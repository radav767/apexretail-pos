import { createRoot } from "react-dom/client";
import "../src/index.css";
import ManagerApprovalDialog from "../src/components/ManagerApprovalDialog";
import { api } from "../src/api/client";

api.defaults.adapter = async (config) => ({ data: { authorization_token: "synthetic-preview-token" }, status: 200, statusText: "OK", headers: {}, config });
createRoot(document.getElementById("root")!).render(<main style={{ background: "#f5f7f8", minHeight: "100vh", padding: 24 }}><h1 style={{ color: "#07583b" }}>ApexRetail POS</h1><p>Central Store · Jamie Patel · Synthetic preview</p><ManagerApprovalDialog companyId="fixture-company" request={{ action: "refund", reason: "Approve this customer refund", context: { original_sale_id: "synthetic-sale" } }} onCancel={() => {}} onApproved={() => {}} /></main>);
