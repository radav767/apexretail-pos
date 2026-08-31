package cloud.apexpos.pos;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.PendingIntent;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.provider.Settings;
import android.hardware.usb.UsbConstants;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbEndpoint;
import android.hardware.usb.UsbInterface;
import android.hardware.usb.UsbManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.util.Base64;
import android.util.Log;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.IOException;
import java.io.OutputStream;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.json.JSONException;
import org.json.JSONObject;

@CapacitorPlugin(
    name = "ApexPrinter",
    permissions = {
        @Permission(
            alias = "bluetooth",
            strings = {
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.BLUETOOTH_SCAN
            }
        )
    }
)
public class ApexPrinterPlugin extends Plugin {
    private static final String TAG = "ApexPrinter";
    private static final String PREFS_NAME = "apex_printer_settings";
    private static final String PREF_CONFIG = "printer_config";
    private static final String ACTION_USB_PERMISSION = "cloud.apexpos.pos.USB_PERMISSION";
    private static final UUID SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb");

    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private PluginCall pendingUsbPermissionCall;
    private BroadcastReceiver usbPermissionReceiver;
    private BroadcastReceiver usbDeviceStateReceiver;
    private boolean bluetoothSettingsOpen;

    @Override
    public void load() {
        super.load();
        usbPermissionReceiver =
            new BroadcastReceiver() {
                @Override
                public void onReceive(Context context, Intent intent) {
                    if (!ACTION_USB_PERMISSION.equals(intent.getAction())) {
                        return;
                    }

                    PluginCall call = pendingUsbPermissionCall;
                    pendingUsbPermissionCall = null;

                    if (call == null) {
                        return;
                    }

                    boolean granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false);
                    JSObject result = new JSObject();
                    result.put("granted", granted);

                    if (granted) {
                        call.resolve(result);
                    } else {
                        call.reject("USB permission denied", "usb_permission_denied");
                    }
                }
            };

        IntentFilter filter = new IntentFilter(ACTION_USB_PERMISSION);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            getContext().registerReceiver(usbPermissionReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            getContext().registerReceiver(usbPermissionReceiver, filter);
        }

        usbDeviceStateReceiver =
            new BroadcastReceiver() {
                @Override
                public void onReceive(Context context, Intent intent) {
                    String action = intent.getAction();
                    if (!UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(action)
                        && !UsbManager.ACTION_USB_DEVICE_DETACHED.equals(action)) {
                        return;
                    }

                    notifyListeners("usbDevicesChanged", new JSObject());
                }
            };

        IntentFilter usbStateFilter = new IntentFilter();
        usbStateFilter.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        usbStateFilter.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            getContext().registerReceiver(usbDeviceStateReceiver, usbStateFilter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            getContext().registerReceiver(usbDeviceStateReceiver, usbStateFilter);
        }
    }

    @Override
    protected void handleOnDestroy() {
        super.handleOnDestroy();
        try {
            getContext().unregisterReceiver(usbPermissionReceiver);
        } catch (IllegalArgumentException ignored) {
        }
        try {
            getContext().unregisterReceiver(usbDeviceStateReceiver);
        } catch (IllegalArgumentException ignored) {
        }
        ioExecutor.shutdownNow();
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        JSObject result = new JSObject();
        result.put("pluginName", "ApexPrinter");
        result.put("packageName", getContext().getPackageName());
        result.put("bridgeAvailable", getBridge() != null);
        result.put("webViewAvailable", getBridge() != null && getBridge().getWebView() != null);
        result.put("androidSdkInt", Build.VERSION.SDK_INT);
        call.resolve(result);
    }

    @PluginMethod
    public void getConfig(PluginCall call) {
        String config = getContext()
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(PREF_CONFIG, null);

        JSObject result = new JSObject();

        if (config == null) {
            result.put("config", defaultConfig());
            call.resolve(result);
            return;
        }

        try {
            result.put("config", new JSONObject(config));
        } catch (JSONException exception) {
            result.put("config", defaultConfig());
        }

        call.resolve(result);
    }

    @PluginMethod
    public void saveConfig(PluginCall call) {
        JSObject config = call.getObject("config");

        if (config == null) {
            call.reject("Printer config is required");
            return;
        }

        getContext()
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(PREF_CONFIG, config.toString())
            .apply();

        JSObject result = new JSObject();
        result.put("config", config);
        call.resolve(result);
    }

    @PluginMethod
    public void clearSavedPrinter(PluginCall call) {
        JSObject cleared = defaultConfig();
        getContext()
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(PREF_CONFIG, cleared.toString())
            .apply();

        JSObject result = new JSObject();
        result.put("config", cleared);
        call.resolve(result);
    }

    @PluginMethod
    public void requestBluetoothAccess(PluginCall call) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            JSObject result = new JSObject();
            result.put("granted", true);
            Log.i(TAG, "Bluetooth permission result: granted=true sdk=" + Build.VERSION.SDK_INT);
            call.resolve(result);
            return;
        }

        if (getPermissionState("bluetooth") == PermissionState.GRANTED) {
            JSObject result = new JSObject();
            result.put("granted", true);
            Log.i(TAG, "Bluetooth permission result: granted=true existing");
            call.resolve(result);
            return;
        }

        requestPermissionForAlias("bluetooth", call, "completeBluetoothPermissionRequest");
    }

    @PluginMethod
    public void getBluetoothStatus(PluginCall call) {
        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();
        JSObject result = new JSObject();
        result.put("available", adapter != null);
        result.put("enabled", adapter != null && adapter.isEnabled());
        call.resolve(result);
    }

    @PluginMethod
    public void listBluetoothPrinters(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
            && getPermissionState("bluetooth") != PermissionState.GRANTED) {
            Log.w(TAG, "Bluetooth bonded device read blocked: permission denied");
            call.reject("Bluetooth permission denied", "bluetooth_permission_denied");
            return;
        }

        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();

        if (adapter == null) {
            call.reject("Bluetooth is not available on this device", "bluetooth_unavailable");
            return;
        }

        JSArray devices = new JSArray();
        Set<BluetoothDevice> bondedDevices = adapter.getBondedDevices();

        if (bondedDevices != null) {
            for (BluetoothDevice device : bondedDevices) {
                devices.put(toBluetoothDevice(device));
            }
        }

        Log.i(
            TAG,
            "Bonded Bluetooth devices returned: " + (bondedDevices == null ? 0 : bondedDevices.size())
        );

        JSObject result = new JSObject();
        result.put("devices", devices);
        call.resolve(result);
    }

    @PluginMethod
    public void openBluetoothSettings(PluginCall call) {
        if (getActivity() == null) {
            call.reject("Android activity is not available", "activity_unavailable");
            return;
        }

        try {
            Intent intent = new Intent(Settings.ACTION_BLUETOOTH_SETTINGS);
            bluetoothSettingsOpen = true;
            getActivity().startActivity(intent);
            call.resolve();
        } catch (Exception exception) {
            call.reject("Unable to open Android Bluetooth settings", "bluetooth_settings_unavailable");
        }
    }

    @PluginMethod
    public void openAppSettings(PluginCall call) {
        if (getActivity() == null) {
            call.reject("Android activity is not available", "activity_unavailable");
            return;
        }

        try {
            Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
            intent.setData(android.net.Uri.fromParts("package", getContext().getPackageName(), null));
            getActivity().startActivity(intent);
            call.resolve();
        } catch (Exception exception) {
            call.reject("Unable to open app settings", "app_settings_unavailable");
        }
    }

    @PluginMethod
    public void listUsbPrinters(PluginCall call) {
        UsbManager usbManager = (UsbManager) getContext().getSystemService(Context.USB_SERVICE);
        JSArray devices = new JSArray();

        for (UsbDevice device : usbManager.getDeviceList().values()) {
            if (!isPlausibleUsbPrinter(device)) {
                continue;
            }
            devices.put(toUsbDevice(usbManager, device));
        }

        JSObject result = new JSObject();
        result.put("devices", devices);
        call.resolve(result);
    }

    @PluginMethod
    public void openPrintSettings(PluginCall call) {
        if (getActivity() == null) {
            call.reject("Android activity is not available", "activity_unavailable");
            return;
        }

        try {
            Intent intent = new Intent(Settings.ACTION_PRINT_SETTINGS);
            if (intent.resolveActivity(getActivity().getPackageManager()) == null) {
                call.reject("Android print settings are not available", "print_settings_unavailable");
                return;
            }
            getActivity().startActivity(intent);
            call.resolve();
        } catch (Exception exception) {
            call.reject("Unable to open Android print settings", "print_settings_unavailable");
        }
    }

    @PluginMethod
    public void requestUsbPermission(PluginCall call) {
        String deviceId = call.getString("deviceId", "");
        UsbManager usbManager = (UsbManager) getContext().getSystemService(Context.USB_SERVICE);
        UsbDevice device = findUsbDevice(usbManager, deviceId);

        if (device == null) {
            call.reject("USB printer is no longer connected", "usb_device_unavailable");
            return;
        }

        if (usbManager.hasPermission(device)) {
            JSObject result = new JSObject();
            result.put("granted", true);
            call.resolve(result);
            return;
        }

        pendingUsbPermissionCall = call;
        PendingIntent pendingIntent = PendingIntent.getBroadcast(
            getContext(),
            0,
            new Intent(ACTION_USB_PERMISSION),
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                ? PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
                : PendingIntent.FLAG_UPDATE_CURRENT
        );
        usbManager.requestPermission(device, pendingIntent);
    }

    @PluginMethod
    public void printReceipt(PluginCall call) {
        String connectionType = call.getString("connectionType", "");
        String printerId = call.getString("printerId", "");
        String rawDataBase64 = call.getString("rawDataBase64", "");
        int copies = Math.max(1, Math.min(5, call.getInt("copies", 1)));

        if (rawDataBase64.isEmpty()) {
            call.reject("Receipt data is required", "missing_receipt_data");
            return;
        }

        byte[] payload = Base64.decode(rawDataBase64, Base64.DEFAULT);

        ioExecutor.execute(() -> {
            try {
                if ("bluetooth".equals(connectionType)) {
                    printBluetooth(printerId, payload, copies);
                } else if ("usb".equals(connectionType)) {
                    printUsb(printerId, payload, copies);
                } else {
                    throw new PrinterException("Unsupported printer connection", "unsupported_connection");
                }

                call.resolve();
            } catch (PrinterException exception) {
                call.reject(exception.getMessage(), exception.code);
            } catch (Exception exception) {
                call.reject(exception.getMessage(), "print_failed");
            }
        });
    }

    @PluginMethod
    public void launchSystemPrint(PluginCall call) {
        String html = call.getString("html", "");
        String jobName = call.getString("jobName", "ApexRetail Receipt");

        if (html.isEmpty()) {
            call.reject("Printable HTML is required", "missing_print_document");
            return;
        }

        Handler mainHandler = new Handler(Looper.getMainLooper());
        mainHandler.post(() -> {
            if (getActivity() == null) {
                call.reject("Android activity is not available", "activity_unavailable");
                return;
            }

            WebView webView = new WebView(getActivity());
            webView.getSettings().setJavaScriptEnabled(false);
            webView.setWebViewClient(
                new WebViewClient() {
                    @Override
                    public void onPageFinished(WebView view, String url) {
                        try {
                            PrintManager printManager = (PrintManager) getActivity().getSystemService(Context.PRINT_SERVICE);

                            if (printManager == null) {
                                call.reject("Android print service is unavailable", "print_service_unavailable");
                                return;
                            }

                            PrintDocumentAdapter adapter = view.createPrintDocumentAdapter(jobName);
                            printManager.print(
                                jobName,
                                adapter,
                                new PrintAttributes.Builder().build()
                            );
                            call.resolve();
                        } catch (Exception exception) {
                            call.reject("Unable to open Android print dialog", "print_dialog_failed");
                        }
                    }

                    @Override
                    public void onReceivedError(
                        WebView view,
                        int errorCode,
                        String description,
                        String failingUrl
                    ) {
                        call.reject("Unable to prepare print document", "print_document_failed");
                    }
                }
            );
            webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
        });
    }

    @PermissionCallback
    public void completeBluetoothPermissionRequest(PluginCall call) {
        boolean granted = getPermissionState("bluetooth") == PermissionState.GRANTED;
        JSObject result = new JSObject();
        result.put("granted", granted);
        Log.i(TAG, "Bluetooth permission result: granted=" + granted);

        if (granted) {
            call.resolve(result);
        } else {
            call.reject("Bluetooth permission denied", "bluetooth_permission_denied");
        }
    }

    @Override
    protected void handleOnResume() {
        super.handleOnResume();
        notifyListeners("printerAppResumed", new JSObject());

        if (!bluetoothSettingsOpen) {
            return;
        }

        bluetoothSettingsOpen = false;
        notifyListeners("bluetoothSettingsClosed", new JSObject());
    }

    private void printBluetooth(String printerId, byte[] payload, int copies) throws Exception {
        if (printerId.isEmpty()) {
            throw new PrinterException("Select a Bluetooth printer first", "bluetooth_printer_missing");
        }

        BluetoothAdapter adapter = BluetoothAdapter.getDefaultAdapter();

        if (adapter == null) {
            throw new PrinterException("Bluetooth is not available on this device", "bluetooth_unavailable");
        }

        BluetoothDevice device;

        try {
            device = adapter.getRemoteDevice(printerId);
        } catch (IllegalArgumentException exception) {
            throw new PrinterException("Selected Bluetooth printer is unavailable", "bluetooth_printer_unavailable");
        }

        if (device == null) {
            throw new PrinterException("Selected Bluetooth printer is unavailable", "bluetooth_printer_unavailable");
        }

        BluetoothSocket socket = null;
        OutputStream outputStream = null;

        try {
            adapter.cancelDiscovery();
            socket = device.createRfcommSocketToServiceRecord(SPP_UUID);
            socket.connect();
            outputStream = socket.getOutputStream();

            for (int copy = 0; copy < copies; copy += 1) {
                outputStream.write(payload);
                outputStream.flush();
            }
        } catch (SecurityException exception) {
            throw new PrinterException("Bluetooth permission denied", "bluetooth_permission_denied");
        } catch (IOException exception) {
            throw new PrinterException("Bluetooth printer disconnected or timed out", "bluetooth_io_error");
        } finally {
            if (outputStream != null) {
                try {
                    outputStream.close();
                } catch (IOException ignored) {
                }
            }
            if (socket != null) {
                try {
                    socket.close();
                } catch (IOException ignored) {
                }
            }
        }
    }

    private void printUsb(String printerId, byte[] payload, int copies) throws Exception {
        if (printerId.isEmpty()) {
            throw new PrinterException("Select a USB printer first", "usb_printer_missing");
        }

        UsbManager usbManager = (UsbManager) getContext().getSystemService(Context.USB_SERVICE);
        UsbDevice device = findUsbDevice(usbManager, printerId);

        if (device == null) {
            throw new PrinterException("USB printer disconnected", "usb_device_unavailable");
        }

        if (!usbManager.hasPermission(device)) {
            throw new PrinterException("USB printer permission denied", "usb_permission_denied");
        }

        UsbInterface usbInterface = findPrintableInterface(device);
        UsbEndpoint endpoint = findBulkOutEndpoint(usbInterface);

        if (usbInterface == null || endpoint == null) {
            throw new PrinterException("This printer may require its Android driver. Try System Printer.", "usb_interface_unsupported");
        }

        UsbDeviceConnection connection = usbManager.openDevice(device);

        if (connection == null) {
            throw new PrinterException("USB printer is unavailable. Reconnect it and try again.", "usb_open_failed");
        }

        try {
            if (!connection.claimInterface(usbInterface, true)) {
                throw new PrinterException("This printer may require its Android driver. Try System Printer.", "usb_claim_failed");
            }

            for (int copy = 0; copy < copies; copy += 1) {
                writeUsbPayload(connection, endpoint, payload);
            }
        } finally {
            try {
                connection.releaseInterface(usbInterface);
            } catch (Exception ignored) {
            }
            connection.close();
        }
    }

    private void writeUsbPayload(UsbDeviceConnection connection, UsbEndpoint endpoint, byte[] payload)
        throws PrinterException {
        int offset = 0;

        while (offset < payload.length) {
            int nextLength = Math.min(4096, payload.length - offset);
            byte[] chunk = new byte[nextLength];
            System.arraycopy(payload, offset, chunk, 0, nextLength);

            int written = connection.bulkTransfer(endpoint, chunk, nextLength, 4000);

            if (written <= 0) {
                throw new PrinterException("Printing did not complete. Check the printer connection, paper, or try System Printer.", "usb_write_failed");
            }

            offset += written;
        }
    }

    private UsbDevice findUsbDevice(UsbManager usbManager, String printerId) {
        for (UsbDevice device : usbManager.getDeviceList().values()) {
            if (String.valueOf(device.getDeviceId()).equals(printerId)) {
                return device;
            }
        }

        return null;
    }

    private UsbInterface findPrintableInterface(UsbDevice device) {
        for (int index = 0; index < device.getInterfaceCount(); index += 1) {
            UsbInterface usbInterface = device.getInterface(index);

            if (usbInterface.getInterfaceClass() == UsbConstants.USB_CLASS_PRINTER
                || usbInterface.getEndpointCount() > 0) {
                return usbInterface;
            }
        }

        return null;
    }

    private boolean isPlausibleUsbPrinter(UsbDevice device) {
        if (device == null) {
            return false;
        }

        if (device.getDeviceClass() == UsbConstants.USB_CLASS_PRINTER) {
            return true;
        }

        String name = ((device.getManufacturerName() == null ? "" : device.getManufacturerName()) + " "
            + (device.getProductName() == null ? "" : device.getProductName())).toLowerCase();

        if (name.contains("printer")
            || name.contains("thermal")
            || name.contains("receipt")
            || name.contains("label")
            || name.contains("pos")) {
            return true;
        }

        for (int index = 0; index < device.getInterfaceCount(); index += 1) {
            UsbInterface usbInterface = device.getInterface(index);
            if (usbInterface.getInterfaceClass() == UsbConstants.USB_CLASS_PRINTER) {
                return true;
            }
        }

        return false;
    }

    private UsbEndpoint findBulkOutEndpoint(UsbInterface usbInterface) {
        if (usbInterface == null) {
            return null;
        }

        for (int endpointIndex = 0; endpointIndex < usbInterface.getEndpointCount(); endpointIndex += 1) {
            UsbEndpoint endpoint = usbInterface.getEndpoint(endpointIndex);
            if (endpoint.getType() == UsbConstants.USB_ENDPOINT_XFER_BULK
                && endpoint.getDirection() == UsbConstants.USB_DIR_OUT) {
                return endpoint;
            }
        }

        return null;
    }

    @SuppressLint("MissingPermission")
    private JSObject toBluetoothDevice(BluetoothDevice device) {
        JSObject result = new JSObject();
        int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.JELLY_BEAN_MR2
            ? device.getType()
            : BluetoothDevice.DEVICE_TYPE_CLASSIC;

        String transport;
        String note = "";

        if (type == BluetoothDevice.DEVICE_TYPE_LE) {
            transport = "ble";
            note = "If this device does not print directly, use System Printer.";
        } else if (type == BluetoothDevice.DEVICE_TYPE_DUAL) {
            transport = "dual";
        } else {
            transport = "classic";
        }

        result.put("id", device.getAddress());
        result.put("shortIdentifier", summarizeBluetoothIdentifier(device.getAddress()));
        result.put("address", device.getAddress());
        result.put("name", device.getName() == null || device.getName().isBlank() ? "Unnamed device" : device.getName());
        result.put("transport", transport);
        result.put("supported", true);
        result.put("note", note);
        result.put("connected", device.getBondState() == BluetoothDevice.BOND_BONDED);
        return result;
    }

    private JSObject toUsbDevice(UsbManager usbManager, UsbDevice device) {
        JSObject result = new JSObject();
        UsbInterface printableInterface = findPrintableInterface(device);
        boolean supported = printableInterface != null && findBulkOutEndpoint(printableInterface) != null;
        String manufacturerName = device.getManufacturerName();
        String productName = device.getProductName();
        String displayName;

        if (manufacturerName != null && !manufacturerName.isBlank()
            && productName != null && !productName.isBlank()) {
            displayName = manufacturerName + " " + productName;
        } else if (productName != null && !productName.isBlank()) {
            displayName = productName;
        } else if (manufacturerName != null && !manufacturerName.isBlank()) {
            displayName = manufacturerName + " printer";
        } else {
            displayName = "Connected USB printer";
        }

        result.put("id", String.valueOf(device.getDeviceId()));
        result.put("name", displayName);
        result.put("shortIdentifier", "USB " + device.getDeviceId());
        result.put("productName", productName);
        result.put("manufacturerName", manufacturerName);
        result.put("vendorId", device.getVendorId());
        result.put("productId", device.getProductId());
        result.put("transport", "usb");
        result.put("supported", supported);
        result.put("connected", true);
        result.put(
            "note",
            supported
                ? (usbManager.hasPermission(device) ? "" : "Select this printer to grant Android USB access.")
                : "This printer may require its Android driver. Try System Printer."
        );
        return result;
    }

    private String summarizeBluetoothIdentifier(String address) {
        if (address == null || address.length() < 5) {
            return "Unknown";
        }

        return address.substring(Math.max(0, address.length() - 8));
    }

    private JSObject defaultConfig() {
        JSObject result = new JSObject();
        result.put("enabled", false);
        result.put("connectionType", "bluetooth");
        result.put("selectedPrinterId", "");
        result.put("selectedPrinterName", "");
        result.put("paperWidth", "80mm");
        result.put("copies", 1);
        result.put("autoPrint", false);
        result.put("cutPaper", false);
        return result;
    }

    private static final class PrinterException extends Exception {
        private final String code;

        private PrinterException(String message, String code) {
            super(message);
            this.code = code;
        }
    }
}
