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
  shop_address_line_1?: string | null;
  shop_address_line_2?: string | null;
  shop_city?: string | null;
  shop_state_province?: string | null;
  shop_country?: string | null;
  shop_phone?: string | null;
  shop_tax_vat_number?: string | null;
  name: string;
  friendly_name: string | null;
  pos_number: number | null;
  device_key: string;
  platform: string | null;
  app_version: string | null;
  last_seen_at: string | null;
  last_seen_platform: string | null;
  last_seen_app_version: string | null;
  status: string;
  claimed_at: string | null;
  deactivated_at: string | null;
  deactivation_reason: string | null;
  removed_at: string | null;
  active: boolean;
};

type Branch = {
  id: string;
  shop_id: string;
  shop_name: string;
  name: string;
};

type DeviceFormState = Record<
  string,
  {
    friendly_name: string;
    pos_number: string;
    branch_id: string;
    deactivation_reason: string;
  }
>;

type ActivationResult = {
  device: Device;
  activation_code: string;
  activation_code_expires_at: string;
};

function requestErrorMessage(error: any, fallback: string) {
  return (
    error?.response?.data?.detail ||
    error?.message ||
    fallback
  );
}

function timeAgo(value: string | null) {
  if (!value) {
    return "Never";
  }

  const diffMs = Date.now() - new Date(value).getTime();
  const diffMinutes = Math.max(0, Math.floor(diffMs / 60000));

  if (diffMinutes < 1) {
    return "Just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  return `${Math.floor(diffHours / 24)}d ago`;
}

function computeDisplayStatus(device: Device) {
  if (device.status === "removed" || device.removed_at) {
    return {
      label: "Removed",
      className: "device-removed",
    };
  }

  if (
    device.status === "deactivated" ||
    device.deactivated_at ||
    !device.active
  ) {
    return {
      label: "Deactivated",
      className: "device-inactive",
    };
  }

  if (!device.last_seen_at) {
    return {
      label: "Active",
      className: "device-active",
    };
  }

  const ageMs =
    Date.now() - new Date(device.last_seen_at).getTime();
  if (ageMs > 5 * 60 * 1000) {
    return {
      label: "Offline",
      className: "device-offline",
    };
  }

  return {
    label: "Active",
    className: "device-active",
  };
}

export default function ShopsDevicesPage({
  companyId,
  embedded = false,
}: {
  companyId: string;
  embedded?: boolean;
}) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [forms, setForms] = useState<DeviceFormState>({});
  const [loading, setLoading] = useState(false);
  const [busyDeviceId, setBusyDeviceId] = useState("");
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [activationResult, setActivationResult] =
    useState<ActivationResult | null>(null);
  const [createForm, setCreateForm] = useState({
    friendly_name: "",
    pos_number: "",
    branch_id: "",
  });

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
        return;
      }

      map.set(branch.shop_id, {
        id: branch.shop_id,
        name: branch.shop_name,
        branches: [branch],
      });
    });

    return Array.from(map.values());
  }, [branches]);

  async function loadData() {
    if (!companyId) {
      return;
    }

    try {
      setLoading(true);
      setError("");

      const [deviceResponse, branchResponse] =
        await Promise.all([
          api.get<Device[]>(`/devices/${companyId}`),
          api.get<Branch[]>(
            `/inventory/branches/${companyId}`,
          ),
        ]);

      const loadedDevices = deviceResponse.data;
      const loadedBranches = branchResponse.data;

      setDevices(loadedDevices);
      setBranches(loadedBranches);
      setForms(
        Object.fromEntries(
          loadedDevices.map((device) => [
            device.id,
            {
              friendly_name:
                device.friendly_name ||
                device.name ||
                "",
              pos_number:
                device.pos_number != null
                  ? String(device.pos_number)
                  : "",
              branch_id: device.branch_id || "",
              deactivation_reason:
                device.deactivation_reason || "",
            },
          ]),
        ),
      );

      if (!createForm.branch_id && loadedBranches[0]?.id) {
        setCreateForm((current) => ({
          ...current,
          branch_id: loadedBranches[0].id,
        }));
      }
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          "Failed to load devices",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, [companyId]);

  function updateForm(
    deviceId: string,
    field: keyof DeviceFormState[string],
    value: string,
  ) {
    setForms((current) => ({
      ...current,
      [deviceId]: {
        ...current[deviceId],
        [field]: value,
      },
    }));
  }

  async function saveDevice(device: Device) {
    const form = forms[device.id];
    const branch = branches.find(
      (item) => item.id === form.branch_id,
    );

    if (!branch) {
      setError("Select a branch.");
      return;
    }

    try {
      setBusyDeviceId(device.id);
      setError("");
      setMessage("");

      await api.patch(
        `/devices/${companyId}/${device.id}`,
        {
          friendly_name: form.friendly_name.trim(),
          pos_number:
            form.pos_number.trim() === ""
              ? null
              : Number(form.pos_number),
          shop_id: branch.shop_id,
          branch_id: branch.id,
        },
      );

      setMessage("POS details saved.");
      await loadData();
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          "Failed to save POS details",
        ),
      );
    } finally {
      setBusyDeviceId("");
    }
  }

  async function updateStatus(
    device: Device,
    status: "active" | "deactivated" | "removed",
  ) {
    const form = forms[device.id];
    try {
      setBusyDeviceId(device.id);
      setError("");
      setMessage("");

      await api.patch(
        `/devices/${companyId}/${device.id}`,
        {
          status,
          deactivation_reason:
            status === "deactivated"
              ? form.deactivation_reason.trim() || null
              : null,
        },
      );

      setMessage(
        status === "active"
          ? "POS access restored."
          : status === "deactivated"
            ? "POS deactivated."
            : "POS access removed.",
      );
      await loadData();
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          "Failed to update POS access",
        ),
      );
    } finally {
      setBusyDeviceId("");
    }
  }

  async function requestActivationCode(
    payload: {
      device_id?: string;
      friendly_name: string;
      pos_number: string;
      branch_id: string;
    },
  ) {
    const branch = branches.find(
      (item) => item.id === payload.branch_id,
    );

    if (!branch) {
      setError("Select a branch.");
      return;
    }

    try {
      if (payload.device_id) {
        setBusyDeviceId(payload.device_id);
      } else {
        setCreating(true);
      }
      setError("");
      setMessage("");
      setActivationResult(null);

      const response = await api.post<ActivationResult>(
        "/devices/activate/request",
        {
          company_id: companyId,
          device_id: payload.device_id,
          friendly_name: payload.friendly_name.trim(),
          pos_number:
            payload.pos_number.trim() === ""
              ? null
              : Number(payload.pos_number),
          shop_id: branch.shop_id,
          branch_id: branch.id,
        },
      );

      setActivationResult(response.data);
      setMessage(
        payload.device_id
          ? "Activation code regenerated."
          : "POS created. Share the code now because it will not be shown again.",
      );
      setCreateForm((current) => ({
        ...current,
        friendly_name: payload.device_id
          ? current.friendly_name
          : "",
        pos_number: payload.device_id
          ? current.pos_number
          : "",
      }));
      await loadData();
    } catch (requestError: any) {
      setError(
        requestErrorMessage(
          requestError,
          "Failed to generate activation code",
        ),
      );
    } finally {
      setBusyDeviceId("");
      setCreating(false);
    }
  }

  function shortenDeviceKey(value: string) {
    if (value.startsWith("pending-")) {
      return "Pending claim";
    }
    if (value.length <= 20) {
      return value;
    }
    return `${value.slice(0, 10)}…${value.slice(-8)}`;
  }

  return (
    <div
      className={`shops-devices-page${embedded ? " embedded" : ""}`}
    >
      <section className="shops-devices-summary">
        <article>
          <span>POS Records</span>
          <strong>{devices.length}</strong>
          <small>Provisioned device access records</small>
        </article>

        <article>
          <span>Live</span>
          <strong>
            {
              devices.filter(
                (device) =>
                  computeDisplayStatus(device).label ===
                  "Active",
              ).length
            }
          </strong>
          <small>Seen within the recent heartbeat window</small>
        </article>

        <article>
          <span>Offline</span>
          <strong>
            {
              devices.filter(
                (device) =>
                  computeDisplayStatus(device).label ===
                  "Offline",
              ).length
            }
          </strong>
          <small>Assigned but not recently seen</small>
        </article>

        <article>
          <span>Disabled</span>
          <strong>
            {
              devices.filter((device) =>
                ["Deactivated", "Removed"].includes(
                  computeDisplayStatus(device).label,
                ),
              ).length
            }
          </strong>
          <small>Cannot create new device activity</small>
        </article>
      </section>

      {activationResult ? (
        <section className="shops-devices-panel activation-code-panel">
          <div>
            <h3>Activation code</h3>
            <p>
              {activationResult.device.friendly_name ||
                activationResult.device.name}
              {" · "}
              expires{" "}
              {new Date(
                activationResult.activation_code_expires_at,
              ).toLocaleString()}
            </p>
          </div>

          <div className="activation-code-value">
            {activationResult.activation_code}
          </div>
        </section>
      ) : null}

      {error ? (
        <p className="shops-devices-message error">{error}</p>
      ) : null}
      {message ? (
        <p className="shops-devices-message success">
          {message}
        </p>
      ) : null}

      <section className="shops-devices-panel">
        <div className="shops-devices-header">
          <div>
            <h2>Add POS</h2>
            <p>
              Create a POS record, assign the branch and
              generate a one-time activation code.
            </p>
          </div>
        </div>

        <div className="device-editor-grid">
          <label>
            Friendly name
            <input
              value={createForm.friendly_name}
              onChange={(event) =>
                setCreateForm((current) => ({
                  ...current,
                  friendly_name: event.target.value,
                }))
              }
              placeholder="Front counter"
            />
          </label>

          <label>
            POS number
            <input
              value={createForm.pos_number}
              onChange={(event) =>
                setCreateForm((current) => ({
                  ...current,
                  pos_number: event.target.value,
                }))
              }
              inputMode="numeric"
              placeholder="1"
            />
          </label>

          <label className="device-editor-wide">
            Branch assignment
            <select
              value={createForm.branch_id}
              onChange={(event) =>
                setCreateForm((current) => ({
                  ...current,
                  branch_id: event.target.value,
                }))
              }
            >
              <option value="">Select branch</option>
              {shops.map((shop) => (
                <optgroup key={shop.id} label={shop.name}>
                  {shop.branches.map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
        </div>

        <div className="device-actions-row">
          <button
            className="device-primary-action"
            disabled={creating}
            onClick={() =>
              void requestActivationCode(createForm)
            }
            type="button"
          >
            {creating ? "Creating..." : "Create POS"}
          </button>
        </div>
      </section>

      <section className="shops-devices-panel">
        <div className="shops-devices-header">
          <div>
            <h2>Devices / POS</h2>
            <p>
              Rename, reassign, regenerate codes, deactivate,
              reactivate or remove access.
            </p>
          </div>

          <button
            onClick={() => void loadData()}
            type="button"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        {!devices.length ? (
          <div className="shops-devices-empty">
            No POS records exist yet.
          </div>
        ) : (
          <div className="device-card-list">
            {devices.map((device) => {
              const form = forms[device.id];
              const branch = branches.find(
                (item) => item.id === form?.branch_id,
              );
              const displayStatus =
                computeDisplayStatus(device);

              return (
                <article
                  className="device-card"
                  key={device.id}
                >
                  <div className="device-card-top">
                    <div>
                      <h3>
                        {device.friendly_name ||
                          device.name}
                      </h3>
                      <p>
                        {device.shop_name || "No shop"}
                        {" · "}
                        {device.branch_name || "No branch"}
                      </p>
                    </div>

                    <span
                      className={displayStatus.className}
                    >
                      {displayStatus.label}
                    </span>
                  </div>

                  <div className="device-meta-grid">
                    <div>
                      <span>POS number</span>
                      <strong>
                        {device.pos_number ?? "Not set"}
                      </strong>
                    </div>
                    <div>
                      <span>Last seen</span>
                      <strong>
                        {timeAgo(device.last_seen_at)}
                      </strong>
                    </div>
                    <div>
                      <span>Platform</span>
                      <strong>
                        {device.last_seen_platform ||
                          device.platform ||
                          "Unknown"}
                      </strong>
                    </div>
                    <div>
                      <span>App version</span>
                      <strong>
                        {device.last_seen_app_version ||
                          device.app_version ||
                          "Unknown"}
                      </strong>
                    </div>
                  </div>

                  <div className="device-key-line">
                    <span>Device key</span>
                    <code title={device.device_key}>
                      {shortenDeviceKey(device.device_key)}
                    </code>
                  </div>

                  <div className="device-editor-grid">
                    <label>
                      Friendly name
                      <input
                        value={form?.friendly_name || ""}
                        onChange={(event) =>
                          updateForm(
                            device.id,
                            "friendly_name",
                            event.target.value,
                          )
                        }
                      />
                    </label>

                    <label>
                      POS number
                      <input
                        value={form?.pos_number || ""}
                        onChange={(event) =>
                          updateForm(
                            device.id,
                            "pos_number",
                            event.target.value,
                          )
                        }
                        inputMode="numeric"
                      />
                    </label>

                    <label className="device-editor-wide">
                      Branch
                      <select
                        value={form?.branch_id || ""}
                        onChange={(event) =>
                          updateForm(
                            device.id,
                            "branch_id",
                            event.target.value,
                          )
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
                            {shop.branches.map((item) => (
                              <option
                                key={item.id}
                                value={item.id}
                              >
                                {item.name}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    </label>

                    <label className="device-editor-wide">
                      Deactivation reason
                      <input
                        value={
                          form?.deactivation_reason || ""
                        }
                        onChange={(event) =>
                          updateForm(
                            device.id,
                            "deactivation_reason",
                            event.target.value,
                          )
                        }
                        placeholder="Optional reason shown in the audit trail"
                      />
                    </label>
                  </div>

                  <div className="device-card-footer">
                    <div className="device-location-copy">
                      <span>
                        Assigned to{" "}
                        {branch?.name ||
                          device.branch_name ||
                          "No branch"}
                      </span>
                      <small>
                        {device.last_seen_at
                          ? new Date(
                              device.last_seen_at,
                            ).toLocaleString()
                          : "No heartbeat received yet"}
                      </small>
                    </div>

                    <div className="device-actions-row">
                      <button
                        className="device-primary-action"
                        disabled={busyDeviceId === device.id}
                        onClick={() => void saveDevice(device)}
                        type="button"
                      >
                        {busyDeviceId === device.id
                          ? "Saving..."
                          : "Save"}
                      </button>
                      <button
                        disabled={busyDeviceId === device.id}
                        onClick={() =>
                          void requestActivationCode({
                            device_id: device.id,
                            friendly_name:
                              form?.friendly_name ||
                              device.friendly_name ||
                              device.name,
                            pos_number:
                              form?.pos_number || "",
                            branch_id:
                              form?.branch_id ||
                              device.branch_id ||
                              "",
                          })
                        }
                        type="button"
                      >
                        Regenerate code
                      </button>
                      {displayStatus.label === "Deactivated" ||
                      displayStatus.label === "Removed" ? (
                        <button
                          onClick={() =>
                            void updateStatus(
                              device,
                              "active",
                            )
                          }
                          type="button"
                        >
                          Reactivate
                        </button>
                      ) : (
                        <button
                          onClick={() =>
                            void updateStatus(
                              device,
                              "deactivated",
                            )
                          }
                          type="button"
                        >
                          Archive terminal
                        </button>
                      )}
                      <button
                        className="device-danger-action"
                        onClick={() =>
                          void updateStatus(
                            device,
                            "removed",
                          )
                        }
                        type="button"
                      >
                        Remove access
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
