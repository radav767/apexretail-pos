import { useState } from "react";
import { api, getApiErrorMessage } from "../api/client";

export type ManagerApprovalRequest = {
  action: "large_discount" | "refund" | "price_override" | "stock_adjustment" | "cash_movement" | "shift_exception" | "print_retry" | "receipt_reprint";
  reason: string;
  context?: Record<string, unknown>;
};

export default function ManagerApprovalDialog({ companyId, request, onApproved, onCancel }: {
  companyId: string; request: ManagerApprovalRequest;
  onApproved: (token: string) => void; onCancel: () => void;
}) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  async function approve() {
    if (!/^\d{4}$/.test(pin)) return setError("Enter the manager's four-digit PIN.");
    try {
      setSaving(true); setError("");
      const response = await api.post("/employees/manager-authorizations", {
        company_id: companyId, manager_pin: pin, action: request.action,
        reason: request.reason, context: request.context || {},
      });
      setPin(""); onApproved(response.data.authorization_token);
    } catch (requestError: unknown) { setError(getApiErrorMessage(requestError, "Manager approval failed.")); }
    finally { setSaving(false); }
  }
  return <div className="pos-manager-approval-backdrop" role="presentation"><section className="pos-manager-approval" role="dialog" aria-modal="true" aria-labelledby="manager-approval-title"><span>Restricted action</span><h2 id="manager-approval-title">Manager approval</h2><p>{request.reason}</p><label>Manager PIN<input autoFocus type="password" inputMode="numeric" maxLength={4} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))} onKeyDown={(event) => { if (event.key === "Enter") void approve(); }}/></label>{error && <p role="alert" className="pos-manager-approval-error">{error}</p>}<div><button onClick={onCancel} disabled={saving}>Cancel</button><button className="primary" onClick={() => void approve()} disabled={saving}>{saving ? "Checking…" : "Authorize"}</button></div></section></div>;
}
