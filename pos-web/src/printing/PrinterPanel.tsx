import { useRef, useState } from "react";
import { api } from "../api/client";
import ManagerApprovalDialog, { type ManagerApprovalRequest } from "../components/ManagerApprovalDialog";
import PrinterManagement from "./PrinterManagement";
import { deliverJob, getOfflinePrintReviews, resolveOfflinePrintReview } from "./queue";

export default function PrinterPanel({ companyId, canManage }: { companyId: string; canManage: boolean }) {
  const [approval, setApproval] = useState<ManagerApprovalRequest | null>(null);
  const callback = useRef<(token: string) => void>(() => {});
  const [reviewReason, setReviewReason] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [, setReviewVersion] = useState(0);
  let reviews: ReturnType<typeof getOfflinePrintReviews> = [];
  try { reviews = getOfflinePrintReviews(companyId); } catch { /* Raw outbox is retained for recovery. */ }
  return <>{reviews.length > 0 && <aside className="printer-notice" role="status"><strong>{reviews.length} offline sale print reviews</strong><p>No automatic receipt or delayed kitchen ticket was sent after synchronization. Inspect existing paper output before reprinting.</p><details><summary>Review sale references</summary><label>Review reason<input value={reviewReason} onChange={e => setReviewReason(e.target.value)} maxLength={240}/></label>{reviewError && <p role="alert">{reviewError}</p>}{reviews.map(r => <div key={r.sale}><p>{r.sale}</p><button disabled={reviewReason.trim().length < 5} onClick={() => {
    void resolveOfflinePrintReview(companyId, r.sale, "already_printed", reviewReason).then(() => setReviewVersion(v => v + 1)).catch(() => setReviewError("Review could not be saved. Nothing was removed."));
  }}>Confirm already printed</button></div>)}</details></aside>}<PrinterManagement companyId={companyId} api={api} deviceId={localStorage.getItem("device_id") || undefined} canManage={canManage} deliver={deliverJob} approve={(request, done) => { callback.current = done; setApproval(request); }}/>{approval && <ManagerApprovalDialog companyId={companyId} request={approval} onCancel={() => setApproval(null)} onApproved={token => { setApproval(null); callback.current(token); }}/>}</>;
}
