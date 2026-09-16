import { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  clearAuthenticationPreservingDeviceIdentity,
  getOrCreateDeviceKey,
  getPinLoginDeviceIdentity,
  rememberDeviceIdentity,
} from "../src/deviceIdentity";
import "../src/index.css";

const companyId = "synthetic-preview-company";
const params = new URLSearchParams(location.search);

export function DeviceIdentityPreview() {
  const [, redraw] = useState(0);
  const refresh = useCallback(() => redraw((value) => value + 1), []);
  const key = getOrCreateDeviceKey(companyId);
  if (!localStorage.getItem("device_id")) {
    rememberDeviceIdentity(companyId, key, "synthetic-terminal", localStorage);
  }
  if (
    params.get("takeover") === "approved"
    && localStorage.getItem("device_key") !== "approved-takeover-device-key"
  ) {
    rememberDeviceIdentity(
      companyId,
      "approved-takeover-device-key",
      "takeover-terminal",
      localStorage,
    );
    localStorage.setItem("employee_token", "takeover-session-token");
  }
  const identity = getPinLoginDeviceIdentity(companyId);

  useEffect(() => {
    const onNavigation = () => refresh();
    window.addEventListener("popstate", onNavigation);
    window.addEventListener("storage", onNavigation);
    return () => {
      window.removeEventListener("popstate", onNavigation);
      window.removeEventListener("storage", onNavigation);
    };
  }, [refresh]);

  return <main style={{ maxWidth: 760, margin: "40px auto", padding: 18 }}>
    <section style={{ padding: 24, borderRadius: 16, background: "white", boxShadow: "0 8px 28px #0001" }}>
      <p style={{ color: "#08745b", fontWeight: 900 }}>SAFE SYNTHETIC IDENTITY</p>
      <h1>Same-device login preview</h1>
      <p>This page never contacts the API. It exposes the exact identity fields the corrected PIN login sends.</p>
      <dl style={{ display: "grid", gridTemplateColumns: "150px minmax(0, 1fr)", gap: 10, overflowWrap: "anywhere" }}>
        <dt>Device key</dt><dd data-device-key>{identity.device_key}</dd>
        <dt>Terminal ID</dt><dd>{identity.device_id || "missing"}</dd>
        <dt>Session token</dt><dd>{identity.session_token ? "present" : "not present"}</dd>
      </dl>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
        <button onClick={() => { localStorage.setItem("employee_id", "synthetic-cashier"); localStorage.setItem("employee_token", "synthetic-session-token"); refresh(); }}>Simulate PIN login</button>
        <button onClick={() => { localStorage.removeItem("employee_id"); localStorage.removeItem("employee_token"); refresh(); }}>Simulate expired auth</button>
        <button onClick={() => { rememberDeviceIdentity(companyId, "approved-takeover-device-key", "takeover-terminal", localStorage); localStorage.setItem("employee_token", "takeover-session-token"); refresh(); }}>Simulate approved takeover</button>
        <button onClick={() => { clearAuthenticationPreservingDeviceIdentity(); refresh(); }}>Simulate full logout</button>
        <button onClick={() => location.reload()}>Reload / app restart</button>
        <button onClick={() => { history.pushState({}, "", "?navigation=forward"); refresh(); }}>Simulate forward navigation</button>
        <button onClick={() => history.back()}>Browser Back</button>
        <button onClick={() => window.open(location.href, "_blank")}>Open second tab</button>
      </div>
      <p style={{ marginTop: 20, color: "#475569" }}>The device key and terminal ID must remain unchanged through every control. A private/incognito window should receive a different device key.</p>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<DeviceIdentityPreview />);
