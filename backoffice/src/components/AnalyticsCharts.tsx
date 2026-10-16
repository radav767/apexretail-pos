import type {
  DashboardBreakdownRow,
  DashboardPhase3Summary,
  DashboardRankedRow,
} from "../dashboard";

type ChartDatum = {
  label: string;
  value: number;
  secondary?: number;
};

const palette = ["#43A047", "#1976D2", "#FF9800", "#7CB342", "#E53935", "#546E7A"];

function compact(value: number) {
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function money(value: number, summary: DashboardPhase3Summary) {
  return `${summary.currency_symbol}${value.toFixed(summary.decimal_places)}`;
}

export function RevenueTrendChart({ summary }: { summary: DashboardPhase3Summary }) {
  const data: ChartDatum[] = summary.trends.map((point) => ({
    label: point.period_start,
    value: Number(point.metrics.net_sales.value || 0),
    secondary: Number(point.metrics.gross_profit.value || 0),
  }));
  const width = 760;
  const height = 260;
  const pad = { left: 46, right: 18, top: 24, bottom: 42 };
  const values = data.flatMap((point) => [point.value, point.secondary || 0]);
  const max = Math.max(...values, 1);
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const x = (index: number) => pad.left + (data.length <= 1 ? innerWidth / 2 : (index * innerWidth) / (data.length - 1));
  const y = (value: number) => pad.top + innerHeight - (value / max) * innerHeight;
  const line = (key: "value" | "secondary") => data.map((point, index) => `${index ? "L" : "M"}${x(index)},${y(point[key] || 0)}`).join(" ");

  if (!data.length) return <div className="chart-empty">No sales trend for this period</div>;

  return <div className="chart-frame">
    <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Net sales and gross profit trend">
      <defs>
        <linearGradient id="revenueArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#43A047" stopOpacity=".26" />
          <stop offset="100%" stopColor="#43A047" stopOpacity=".02" />
        </linearGradient>
      </defs>
      {[0, .25, .5, .75, 1].map((ratio) => <g key={ratio}>
        <line x1={pad.left} x2={width - pad.right} y1={pad.top + innerHeight * ratio} y2={pad.top + innerHeight * ratio} className="chart-gridline" />
        <text x={pad.left - 8} y={pad.top + innerHeight * ratio + 4} textAnchor="end" className="chart-axis-label">{compact(max * (1 - ratio))}</text>
      </g>)}
      <path d={`${line("value")} L${x(data.length - 1)},${pad.top + innerHeight} L${x(0)},${pad.top + innerHeight} Z`} fill="url(#revenueArea)" />
      <path d={line("value")} className="chart-line chart-line-primary" />
      <path d={line("secondary")} className="chart-line chart-line-secondary" />
      {data.map((point, index) => <g key={`${point.label}-${index}`}>
        <circle cx={x(index)} cy={y(point.value)} r="5" className="chart-point chart-point-primary"><title>{`${point.label}: net sales ${money(point.value, summary)}`}</title></circle>
        <circle cx={x(index)} cy={y(point.secondary || 0)} r="4" className="chart-point chart-point-secondary"><title>{`${point.label}: gross profit ${money(point.secondary || 0, summary)}`}</title></circle>
        {(index === 0 || index === data.length - 1 || data.length <= 5) && <text x={x(index)} y={height - 14} textAnchor="middle" className="chart-axis-label">{point.label.slice(5)}</text>}
      </g>)}
    </svg>
    <div className="chart-legend"><span><i className="legend-leaf" />Net sales</span><span><i className="legend-blue" />Gross profit</span></div>
  </div>;
}

export function RankedBarChart({ rows, summary }: { rows: DashboardRankedRow[]; summary: DashboardPhase3Summary }) {
  const data = rows.slice(0, 6).map((row) => ({ label: row.name, value: Number(row.revenue) }));
  const max = Math.max(...data.map((row) => row.value), 1);
  if (!data.length) return <div className="chart-empty">No product sales for this period</div>;
  return <div className="bar-chart" role="img" aria-label="Top-selling products by revenue">
    {data.map((row, index) => <div className="bar-chart-row" key={`${row.label}-${index}`} title={`${row.label}: ${money(row.value, summary)}`}>
      <span className="bar-label">{row.label}</span>
      <span className="bar-track"><span className="bar-fill" style={{ width: `${Math.max(4, (row.value / max) * 100)}%`, background: palette[index % palette.length] }} /></span>
      <strong>{money(row.value, summary)}</strong>
    </div>)}
  </div>;
}

export function PaymentDonutChart({ rows, summary }: { rows: DashboardBreakdownRow[]; summary: DashboardPhase3Summary }) {
  const data = rows.filter((row) => Number(row.net_sales) > 0).slice(0, 6);
  const total = data.reduce((sum, row) => sum + Number(row.net_sales), 0);
  if (!data.length || total <= 0) return <div className="chart-empty">No payment totals for this period</div>;
  let offset = 0;
  const segments = data.map((row, index) => {
    const share = Number(row.net_sales) / total;
    const segment = { ...row, share, offset, color: palette[index % palette.length] };
    offset += share;
    return segment;
  });
  return <div className="donut-layout">
    <svg className="donut-chart" viewBox="0 0 220 220" role="img" aria-label="Payment method share of net sales">
      <circle cx="110" cy="110" r="78" className="donut-track" />
      {segments.map((segment) => <circle key={segment.key} cx="110" cy="110" r="78" fill="none" stroke={segment.color} strokeWidth="25" pathLength="1" strokeDasharray={`${segment.share} ${1 - segment.share}`} strokeDashoffset={-segment.offset} transform="rotate(-90 110 110)"><title>{`${segment.name}: ${money(Number(segment.net_sales), summary)}`}</title></circle>)}
      <text x="110" y="104" textAnchor="middle" className="donut-caption">Net sales</text>
      <text x="110" y="128" textAnchor="middle" className="donut-total">{money(total, summary)}</text>
    </svg>
    <div className="donut-legend">{segments.map((segment) => <div key={segment.key}><i style={{ background: segment.color }} /><span>{segment.name}</span><strong>{Math.round(segment.share * 100)}%</strong></div>)}</div>
  </div>;
}
