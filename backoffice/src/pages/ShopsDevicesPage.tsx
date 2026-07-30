import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import "./shops-devices.css";

type Device = {
  id: string;
  company_id: string;
  shop_id: string | null;
  branch_id: string | null;
  shop_name: string | null;
  branch_name: string | null;
  name: string;
  device_key: string;
  platform: string | null;
  app_version: string | null;
  active: boolean;
};

type Branch = {
  id: string;
  shop_id: string;
  shop_name: string;
  name: string;
};

export default function ShopsDevicesPage({
  companyId,
}: {
  companyId: string;
}) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [assignments, setAssignments] =
    useState<Record<string, string>>({});

  const [loadingDeviceId, setLoadingDeviceId] =
    useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const shops = useMemo(() => {
    const map = new Map<
      string,
      {
        id: string;
        name: string;
        branches: Branch[];
      }
    >();

    branches.forEach((branch) => {
      const existing = map.get(branch.shop_id);

      if (existing) {
        existing.branches.push(branch);
      } else {
        map.set(branch.shop_id, {
          id: branch.shop_id,
          name: branch.shop_name,
          branches: [branch],
        });
      }
    });

    return Array.from(map.values());
  }, [branches]);

  async function loadData() {
    if (!companyId) return;

    try {
      setLoading(true);
      setMessage("");

      const [deviceResponse, branchResponse] =
        await Promise.all([
          api.get(`/devices/${companyId}`),
          api.get(`/inventory/branches/${companyId}`),
        ]);

      const loadedDevices: Device[] = deviceResponse.data;
      const loadedBranches: Branch[] = branchResponse.data;

      setDevices(loadedDevices);
      setBranches(loadedBranches);

      const selected: Record<string, string> = {};

      loadedDevices.forEach((device) => {
        selected[device.id] =
          device.branch_id ||
          loadedBranches[0]?.id ||
          "";
      });

      setAssignments(selected);
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to load shops and devices",
      );
    } finally {
      setLoading(false);
    }
  }

  async function saveAssignment(device: Device) {
    const selectedBranchId = assignments[device.id];

    const branch = branches.find(
      (item) => item.id === selectedBranchId,
    );

    if (!branch) {
      setMessage("Select a valid branch");
      return;
    }

    try {
      setLoadingDeviceId(device.id);
      setMessage("");

      await api.patch(
        `/devices/${companyId}/${device.id}/assignment`,
        {
          shop_id: branch.shop_id,
          branch_id: branch.id,
        },
      );

      setMessage(
        `${device.name} assigned to ${branch.name}`,
      );

      await loadData();
    } catch (error: any) {
      setMessage(
        error.response?.data?.detail ||
          "Failed to update device assignment",
      );
    } finally {
      setLoadingDeviceId("");
    }
  }

  function shortenDeviceKey(value: string) {
    if (value.length <= 20) return value;

    return `${value.slice(0, 10)}…${value.slice(-8)}`;
  }

  useEffect(() => {
    void loadData();
  }, [companyId]);

  return (
    <div className="shops-devices-page">
      <section className="shops-devices-summary">
        <article>
          <span>Shops</span>
          <strong>{shops.length}</strong>
          <small>Active business locations</small>
        </article>

        <article>
          <span>Branches</span>
          <strong>{branches.length}</strong>
          <small>Inventory locations</small>
        </article>

        <article>
          <span>Devices</span>
          <strong>{devices.length}</strong>
          <small>Registered POS installations</small>
        </article>

        <article>
          <span>Active Devices</span>
          <strong>
            {devices.filter((device) => device.active).length}
          </strong>
          <small>Ready for sales</small>
        </article>
      </section>

      <section className="shops-devices-panel">
        <div className="shops-devices-header">
          <div>
            <h2>Registered POS Devices</h2>
            <p>
              Assign each POS installation to the branch whose
              stock it should use.
            </p>
          </div>

          <button
            type="button"
            onClick={loadData}
            disabled={loading}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        {!devices.length ? (
          <div className="shops-devices-empty">
            No POS devices have registered yet. Open and log in
            to the POS to register a device.
          </div>
        ) : (
          <div className="shops-devices-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Platform</th>
                  <th>Device Key</th>
                  <th>Current Location</th>
                  <th>Assign Branch</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>

              <tbody>
                {devices.map((device) => (
                  <tr key={device.id}>
                    <td>
                      <strong>{device.name}</strong>
                      <small>
                        Version {device.app_version || "—"}
                      </small>
                    </td>

                    <td>
                      {(device.platform || "Unknown")
                        .toUpperCase()}
                    </td>

                    <td>
                      <code title={device.device_key}>
                        {shortenDeviceKey(device.device_key)}
                      </code>
                    </td>

                    <td>
                      <strong>
                        {device.branch_name || "Unassigned"}
                      </strong>
                      <small>
                        {device.shop_name || "No shop"}
                      </small>
                    </td>

                    <td>
                      <select
                        value={assignments[device.id] || ""}
                        onChange={(event) =>
                          setAssignments((current) => ({
                            ...current,
                            [device.id]: event.target.value,
                          }))
                        }
                      >
                        <option value="">
                          Select branch
                        </option>

                        {shops.map((shop) => (
                          <optgroup
                            key={shop.id}
                            label={shop.name}
                          >
                            {shop.branches.map((branch) => (
                              <option
                                key={branch.id}
                                value={branch.id}
                              >
                                {branch.name}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    </td>

                    <td>
                      <span
                        className={
                          device.active
                            ? "device-active"
                            : "device-inactive"
                        }
                      >
                        {device.active
                          ? "Active"
                          : "Inactive"}
                      </span>
                    </td>

                    <td>
                      <button
                        type="button"
                        className="device-save-button"
                        onClick={() =>
                          saveAssignment(device)
                        }
                        disabled={
                          loadingDeviceId === device.id ||
                          !assignments[device.id]
                        }
                      >
                        {loadingDeviceId === device.id
                          ? "Saving..."
                          : "Save"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="shops-list-panel">
        <div className="shops-devices-header">
          <div>
            <h2>Shops and Branches</h2>
            <p>
              Inventory locations currently available to POS
              devices.
            </p>
          </div>
        </div>

        <div className="shop-location-grid">
          {shops.map((shop) => (
            <article key={shop.id}>
              <h3>{shop.name}</h3>

              {shop.branches.map((branch) => (
                <div key={branch.id}>
                  <span>{branch.name}</span>
                  <small>
                    {
                      devices.filter(
                        (device) =>
                          device.branch_id === branch.id,
                      ).length
                    }{" "}
                    device(s)
                  </small>
                </div>
              ))}
            </article>
          ))}
        </div>
      </section>

      <p className="shops-devices-message">{message}</p>
    </div>
  );
}
