import type { ComponentType, SVGProps } from "react";
import {
  ArrowLeftIcon,
  ArrowsRightLeftIcon,
  BanknotesIcon,
  ChartBarIcon,
  ClockIcon,
  Cog6ToothIcon,
  CubeIcon,
  DocumentChartBarIcon,
  PrinterIcon,
  ReceiptPercentIcon,
  Squares2X2Icon,
} from "@heroicons/react/24/outline";

export type PosFeatureIcon =
  | "adjust" | "cash" | "chart" | "clock" | "inventory" | "printer"
  | "receipt" | "report" | "settings" | "transfer" | "void";

const icons: Record<PosFeatureIcon, ComponentType<SVGProps<SVGSVGElement>>> = {
  adjust: ArrowsRightLeftIcon,
  cash: BanknotesIcon,
  chart: ChartBarIcon,
  clock: ClockIcon,
  inventory: CubeIcon,
  printer: PrinterIcon,
  receipt: ReceiptPercentIcon,
  report: DocumentChartBarIcon,
  settings: Cog6ToothIcon,
  transfer: Squares2X2Icon,
  void: ReceiptPercentIcon,
};

export type PosFeatureItem<T extends string> = {
  id: T;
  title: string;
  detail: string;
  icon: PosFeatureIcon;
  permitted?: boolean;
};

export function PosFeatureHub<T extends string>({
  title,
  features,
  onSelect,
}: {
  title: string;
  features: PosFeatureItem<T>[];
  onSelect: (feature: T) => void;
}) {
  return <section className="pos-module-card pos-feature-hub" aria-labelledby="pos-feature-hub-title">
    <div className="pos-module-card-heading"><div><h2 id="pos-feature-hub-title">{title}</h2></div></div>
    <div className="pos-feature-grid">
      {features.filter((feature) => feature.permitted !== false).map((feature) => {
        const Icon = icons[feature.icon];
        return <button type="button" key={feature.id} onClick={() => onSelect(feature.id)}>
          <span className="pos-feature-icon"><Icon /></span>
          <span><strong>{feature.title}</strong><small>{feature.detail}</small></span>
        </button>;
      })}
    </div>
  </section>;
}

export function PosFeatureBack({ label, onClick }: { label: string; onClick: () => void }) {
  return <button type="button" className="pos-feature-back" onClick={onClick}>
    <ArrowLeftIcon /> Back to {label}
  </button>;
}
