package cloud.apexpos.pos;

import java.net.InetSocketAddress;

/** DNS-free private-network allowlist shared by the bridge and JVM checks. */
public final class PrinterNetworkTarget {
    private PrinterNetworkTarget() {}

    public static InetSocketAddress parse(String value) {
        if (value == null || !value.matches("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}:9100")) {
            throw new IllegalArgumentException("Use a private LAN IPv4 address on port 9100");
        }
        String host = value.substring(0, value.lastIndexOf(':'));
        String[] octets = host.split("\\.");
        int[] ip = new int[4];
        for (int i = 0; i < 4; i++) {
            ip[i] = Integer.parseInt(octets[i]);
            if (ip[i] > 255 || !Integer.toString(ip[i]).equals(octets[i])) {
                throw new IllegalArgumentException("Invalid LAN address");
            }
        }
        if (!(ip[0] == 10 || (ip[0] == 172 && ip[1] >= 16 && ip[1] <= 31) || (ip[0] == 192 && ip[1] == 168))) {
            throw new IllegalArgumentException("Printer must be on a private LAN");
        }
        return new InetSocketAddress(host, 9100);
    }
}
