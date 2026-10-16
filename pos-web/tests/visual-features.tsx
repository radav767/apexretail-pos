import { createRoot } from "react-dom/client";
import { useState } from "react";
import "../src/index.css";
import "../src/pos-modules.css";
import "../src/premium-theme.css";
import PosSessionHeader from "../src/components/PosSessionHeader";
import { PosFeatureBack, PosFeatureHub, type PosFeatureItem } from "../src/components/PosFeatureHub";

type Feature = "home" | "transaction-history" | "cancel-void-sales" | "credit-settlement" | "cashier-shifts" | "z-reports" | "goods-received" | "stock-adjustments" | "inventory-overview" | "inventory-activity";
const sales: PosFeatureItem<Feature>[] = [
  { id: "transaction-history", title: "Transaction History", detail: "View completed sales and receipts", icon: "clock" },
  { id: "cancel-void-sales", title: "Cancel / Void Sales", detail: "Review permitted refunds and void actions", icon: "void" },
  { id: "credit-settlement", title: "Credit Settlement", detail: "Manage supported customer settlements", icon: "cash" },
  { id: "cashier-shifts", title: "Cashier Shifts", detail: "Open, reconcile and close this shift", icon: "transfer" },
  { id: "z-reports", title: "Z Reports", detail: "View and reprint immutable reports", icon: "report" },
];
const inventory: PosFeatureItem<Feature>[] = [
  { id: "goods-received", title: "Goods Received (GRN)", detail: "Receive stock from suppliers", icon: "inventory" },
  { id: "stock-adjustments", title: "Stock Adjustments", detail: "Record corrections and physical counts", icon: "adjust" },
  { id: "inventory-overview", title: "Inventory Overview", detail: "Review current branch balances", icon: "chart" },
  { id: "inventory-activity", title: "Inventory Activity", detail: "Review auditable stock movements", icon: "clock" },
];

function Preview() {
  const mode = new URLSearchParams(location.search).get("view") === "inventory" ? "Inventory" : "Sales Management";
  const [selected, setSelected] = useState<Feature>("home");
  const features = mode === "Inventory" ? inventory : sales;
  return <main className="pos-module-overlay" style={{ position: "relative", inset: 0, minHeight: "100vh" }}><section className="pos-module-container">
    <PosSessionHeader title={selected === "home" ? mode : features.find((item) => item.id === selected)?.title || mode} cashierName="Tariro Moyo" shopName="Harare Central" branchName="Main Floor" shiftStatus="open" />
    {selected === "home" ? <PosFeatureHub title={mode} features={features} onSelect={setSelected} /> : <><PosFeatureBack label={mode} onClick={() => setSelected("home")} /><section className="pos-module-card"><h2>{features.find((item) => item.id === selected)?.title}</h2><p>Synthetic preview only. The production page keeps its existing permissions, API data and actions.</p></section></>}
  </section></main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
