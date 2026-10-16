import { useEffect, useState, type ReactNode } from "react";
import { ClockIcon, MapPinIcon, UserCircleIcon } from "@heroicons/react/24/outline";

type Props = {
  title: string;
  eyebrow?: string;
  cashierName: string;
  shopName: string;
  branchName: string;
  shiftStatus: string;
  actions?: ReactNode;
};

export default function PosSessionHeader({
  title,
  eyebrow = "ApexRetail POS",
  cashierName,
  shopName,
  branchName,
  shiftStatus,
  actions,
}: Props) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  return <header className="pos-workspace-header">
    <div className="pos-workspace-title">
      <span className="pos-workspace-eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <div className="pos-workspace-meta">
        <span><MapPinIcon />{shopName}{branchName && branchName !== shopName ? ` · ${branchName}` : ""}</span>
        <span><UserCircleIcon />{cashierName}</span>
        <span><ClockIcon />{now.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" })} · {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
      </div>
    </div>
    <div className="pos-workspace-actions">
      <span className={`pos-shift-chip ${shiftStatus.toLowerCase() === "open" ? "is-open" : ""}`}><i />Shift {shiftStatus || "closed"}</span>
      {actions}
    </div>
  </header>;
}
