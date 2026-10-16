# ApexPOS Phase 5 Design Specification

## Product character

ApexPOS should feel like focused commercial retail software: calm white workspaces,
leaf-green brand actions, concise status language, dense but readable operational
data, and clear financial confirmation steps. Decoration must never compete with
the sale, inventory, shift, or reporting task.

## Brand tokens

| Role | Token | Value |
| --- | --- | --- |
| Primary | Leaf green | `#43A047` |
| Primary dark | Deep leaf | `#2E7D32` |
| Accent | Orange | `#FF9800` |
| Information | Blue | `#1976D2` |
| Danger | Red | `#E53935` |
| Ink | Black | `#17212B` |
| Canvas | Mist | `#F4F7F5` |
| Surface | White | `#FFFFFF` |

The primary action in each view is leaf green. Orange is reserved for attention
and cash-related accents, blue for neutral information, and red for destructive
or failed states. Financial values use tabular numerals.

## Geometry and motion

- Spacing follows a 4 px base scale, with 8, 12, 16, 20, 24 and 32 px steps.
- Controls are at least 44 px high on touch devices and 40 px on desktop.
- Cards use 16–20 px radii; inputs and buttons use 10–14 px radii.
- Shadows are restrained and paired with a quiet border so cards remain clear
  in low-contrast displays.
- State transitions use 140–180 ms ease-out motion. Reduced-motion preferences
  disable nonessential movement.

## Typography

The native Inter/system stack is retained for offline and Android WebView
reliability. Titles use 700–800 weight and tight tracking. Body copy uses
400–600. Operational screens avoid explanatory paragraphs; safety, security,
validation, and financial confirmation copy remains visible.

## Responsive behavior

- Phone (`320–599 px`): one-column forms, full-width primary actions, bottom-sheet
  dialogs, compact cards, horizontally scrollable data tables only where a card
  representation would lose financial meaning.
- Tablet (`600–1023 px`): two-column grids and an expanded checkout workspace.
- Desktop (`1024 px+`): persistent Backoffice sidebar, two-pane checkout, compact
  analytics grids, and constrained readable content widths.
- Every grid child uses `min-width: 0`; dialogs and form controls use `max-width:
  100%`; the document never scrolls horizontally.

## Shared component patterns

- `PageHeader`: title, concise context, and the primary page action.
- `MetricCard`: icon/accent, label, value, comparison, and optional drill-down.
- `Panel`: white bordered surface with consistent header and action placement.
- `StatusPill`: success, warning, danger, info, or neutral state.
- `EmptyState`: icon, short outcome statement, optional action.
- `Alert`: security and financial messages with explicit severity.
- `ChartCard`: accessible SVG chart backed by live API values and a tabular
  fallback or detailed table.
- `Dialog`: constrained modal on desktop and accessible bottom sheet on phones.

## Information architecture

POS keeps Sales as the immediate workspace. Sales Management contains history,
customers, credit, expenses, and Shift Management. Backoffice navigation groups
Overview, Sales Management, Catalogue, Operations, People, and Configuration.
Permissions continue to decide which actions and modules are rendered.

## Data and safety

Charts, totals, badges, and status labels are projections of existing API
responses only. The UI does not infer or recalculate authoritative shift or
financial totals. Identifiers needed for support remain in technical/export
contexts but are not presented as primary cashier-facing content.
