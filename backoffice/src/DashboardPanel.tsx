import { dashboardRangeOptions, formatDashboardMoney, type DashboardMetric, type DashboardPhase2Summary, type DashboardRangeKey } from "./dashboard";

type DashboardPanelProps = {
  summary: DashboardPhase2Summary | null;
  shops?: DashboardPhase2Summary["shops"];
  rangeKey: DashboardRangeKey;
  selectedShopId: string;
  customDateFrom: string;
  customDateTo: string;
  onRangeChange: (value: DashboardRangeKey) => void;
  onShopChange: (value: string) => void;
  onDateFromChange: (value: string) => void;
  onDateToChange: (value: string) => void;
};

export function DashboardPanel({
  summary,
  shops,
  rangeKey,
  selectedShopId,
  customDateFrom,
  customDateTo,
  onRangeChange,
  onShopChange,
  onDateFromChange,
  onDateToChange,
}: DashboardPanelProps) {
  const cards = summary
    ? [
        ["Gross Sales", summary.metrics.gross_sales],
        ["Net Sales", summary.metrics.net_sales],
        ["Cost of Sales", summary.metrics.cost_of_sales],
        ["Gross Profit", summary.metrics.gross_profit],
        ["Discounts", summary.metrics.discounts],
        ["Refunds", summary.metrics.refunds],
      ] as Array<[string, DashboardMetric]>
    : [];

  return (
    <>
      <section className="dashboard-filters panel">
        <div className="panel-header">
          <div>
            <h2>Reporting Filters</h2>
            <p>
              Completed sales only. Reporting timezone:{" "}
              {summary?.reporting_timezone || "Africa/Harare"}
            </p>
          </div>
        </div>

        <div className="dashboard-filter-grid">
          <label className="dashboard-filter-field">
            <span>Reporting period</span>
            <select
              aria-label="Reporting period"
              value={rangeKey}
              onChange={(event) =>
                onRangeChange(event.target.value as DashboardRangeKey)
              }
            >
              {dashboardRangeOptions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="dashboard-filter-field">
            <span>Shop</span>
            <select
              aria-label="Shop"
              value={selectedShopId}
              onChange={(event) => onShopChange(event.target.value)}
            >
              <option value="">All shops</option>
              {(shops ?? summary?.shops ?? []).map((shop) => (
                <option key={shop.id} value={shop.id}>
                  {shop.name}
                </option>
              ))}
            </select>
          </label>

          {rangeKey === "custom" && (
            <>
              <label className="dashboard-filter-field">
                <span>Date from</span>
                <input
                  aria-label="Date from"
                  type="date"
                  value={customDateFrom}
                  onChange={(event) => onDateFromChange(event.target.value)}
                />
              </label>
              <label className="dashboard-filter-field">
                <span>Date to</span>
                <input
                  aria-label="Date to"
                  type="date"
                  value={customDateTo}
                  onChange={(event) => onDateToChange(event.target.value)}
                />
              </label>
            </>
          )}
        </div>

        {summary && (
          <p className="dashboard-range-caption">
            Showing {summary.date_from} to {summary.date_to}
            {summary.shop_id
              ? " for one shop"
              : " across all company shops"}
            .
          </p>
        )}
      </section>

      <section className="summary-grid">
        {cards.map(([title, metric]) => (
          <article
            className={`summary-card ${metric.available ? "" : "muted"}`}
            key={title}
          >
            <span>{title}</span>
            <strong>
              {formatDashboardMoney(
                metric,
                summary?.currency_symbol || "$",
                summary?.decimal_places ?? 2,
              )}
            </strong>
            <small>
              {metric.available
                ? "Completed sales and recorded refunds"
                : "Not currently measurable"}
            </small>
            {metric.reason ? <p>{metric.reason}</p> : null}
          </article>
        ))}
      </section>
    </>
  );
}
