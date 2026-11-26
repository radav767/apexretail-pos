import { useRef, useState } from "react";
import { api } from "../api/client";
import ManagerApprovalDialog, { type ManagerApprovalRequest } from "../components/ManagerApprovalDialog";
import { deliverJob, scheduleSalePrint } from "../printing/queue";
import BusinessOperations from "./BusinessOperations";

export default function BusinessPanel({ companyId, branchId, employeeId, onPrintReceipt, onProductsChanged,onOpenBackoffice }: { onOpenBackoffice?:()=>void;companyId: string; branchId: string; employeeId?: string; onPrintReceipt: (id: string) => Promise<void>; onProductsChanged?: () => void }) {
  const [request, setRequest] = useState<ManagerApprovalRequest | null>(null);
  const callback = useRef<(token: string) => void>(() => {});
  return <><BusinessOperations surface="pos" onOpenBackoffice={onOpenBackoffice} companyId={companyId} api={api} branchId={branchId} recoveryEmployeeId={employeeId} deviceId={localStorage.getItem("device_id") || ""} deliver={deliverJob} onPrintReceipt={onPrintReceipt}
    onSaleCompleted={async id => { onProductsChanged?.(); await scheduleSalePrint(companyId, id); }} approve={(next, done) => { callback.current = done; setRequest(next); }}/>
    {request && <ManagerApprovalDialog companyId={companyId} request={request} onCancel={() => setRequest(null)} onApproved={token => { setRequest(null); callback.current(token); }}/>}</>;
}
