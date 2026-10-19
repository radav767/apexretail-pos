package cloud.apexpos.pos;

/** Runs on a local JDK without packaging/installing an APK or opening sockets. */
public final class PrinterNetworkTargetCheck {
    public static void main(String[] args) {
        String[] valid = {"10.0.0.8:9100", "172.16.2.3:9100", "172.31.255.254:9100", "192.168.1.50:9100"};
        for (String value : valid) {
            if (PrinterNetworkTarget.parse(value).getPort() != 9100) throw new AssertionError(value);
        }
        String[] invalid = {"localhost:9100", "127.0.0.1:9100", "169.254.169.254:9100", "8.8.8.8:9100", "192.168.1.5:22", "192.168.01.2:9100", "172.32.1.2:9100", "192.168.256.1:9100", "10.1.2.3:9100\n", "[::1]:9100"};
        for (String value : invalid) {
            try { PrinterNetworkTarget.parse(value); throw new AssertionError("Accepted " + value); }
            catch (IllegalArgumentException expected) { /* Fail closed. */ }
        }
        System.out.println("PASS: 4 private endpoints and 10 forbidden endpoints; no network connections made");
    }
}
