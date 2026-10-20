"""Join explicit test evidence and UI inventory without inferring E2E success."""
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
output = root / "phase7e-evidence/stabilization/audit"
output.mkdir(parents=True, exist_ok=True)
cases = ET.parse("/tmp/phase7e-stabilization-backend.xml").getroot().findall(".//testcase")
rows = []
for case in cases:
    result = "FAIL" if case.find("failure") is not None or case.find("error") is not None else "SKIP" if case.find("skipped") is not None else "PASS"
    rows.append(dict(feature=case.get("classname"), action=case.get("name"), test_result=result,
        remaining_limitation="Automated backend behavior only; not proof of every frontend action or physical device.",
        evidence="backend-regression.xml", verification_type="automated backend test"))
frontend = json.loads((root / "phase7e-evidence/stabilization/frontend/frontend-test-results.json").read_text())
for test in frontend:
    rows.append(dict(feature=test["project"], action=test["script"], test_result=test["status"],
        remaining_limitation="Command-level evidence; source/static assertions are not authenticated browser E2E.",
        evidence=f"frontend/{test['project']}-{test['script'].replace(':','-')}.log", verification_type="automated frontend command"))
for path in (root / "phase7e-evidence/stabilization/preview/checks.json", root / "phase7e-evidence/tips/preview/checks.json",
        root / "phase7e-evidence/screenshots/employees/responsive-checks.json",
        root / "phase7e-evidence/screenshots/printers/responsive-checks.json",
        root / "phase7e-evidence/screenshots/business/responsive-checks.json",
        root / "phase7e-evidence/screenshots/phase7e-extra-checks.json"):
    if not path.exists(): continue
    evidence = json.loads(path.read_text())
    for check in evidence["checks"]:
        rows.append(dict(feature=f"{check.get('feature', check.get('view'))}/{check.get('device','all')}", action=json.dumps(check, sort_keys=True),
            test_result="PASS", remaining_limitation="Actual React components with synthetic API adapter; physical Android/hardware and full authentication not exercised.",
            evidence=str(path.relative_to(root)), verification_type="automated component browser action"))
source = json.loads((output / "ui-action-inventory.json").read_text())
for control in source["rows"]:
    rows.append({**{key: control[key] for key in ("feature", "action", "test_result", "remaining_limitation")},
        "evidence": control["source"], "verification_type": "source inventory; runtime action unverified"})
manual = [
    ("Navigation", "Stock Transfers, Sales Reports and Top Selling Products dedicated POS destinations", "BLOCKED", "Existing menu entries still open a generic hub; no dedicated matching POS feature is implemented."),
    ("Pharmacy", "Lot-level transfers, physical counts and held-versus-saleable totals on all old clients", "NOT VERIFIED", "Lot receive/remove/returns verified; legacy transfer/count and generic reports need lot-aware acceptance."),
    ("Inventory valuation", "Include variant balances and variant costs in legacy inventory/valuation dashboards", "BLOCKED", "Current valuation queries read parent inventory_balances/products only; variant inventory is a separate ledger dimension and is omitted. Do not certify comprehensive valuation."),
    ("Offline restaurant", "Create new unpaid drafts after cold restart with no verified profile", "BLOCKED", "Recovery is available for the authenticated cashier; new drafts remain disabled until profile/permissions reload. No unsigned permission cache was added."),
    ("Offline restaurant", "Offline kitchen dispatch, payment, transfer and merge", "UNSUPPORTED", "Intentionally fail closed. Only unpaid draft/edits synchronize with original identity and version checks."),
    ("Authentication", "Physical Android cold restart, backgrounding and cashier PIN restoration", "NOT TESTED", "Requires installed device and existing session; no APK installation/storage reset performed."),
    ("Printing", "Physical Bluetooth, USB, LAN, 58mm/80mm margins, cutter and KOT routing", "NOT TESTED", "Source/JVM/queue/browser layout checks do not establish hardware delivery."),
    ("Tips and service charges", "Accountant/legal approval, gateway/payroll integration and automatic percentage charges", "REVIEW REQUIRED", "Separate confirmed-transfer ledger tested; no gateway/payroll/automatic charges are claimed."),
    ("Production rollout", "Current backup, protected runner/runtime role, coordinated backend/web/old APK acceptance", "NOT VERIFIED", "Archived October 16 backup only. Production was not connected to or modified."),
]
for feature, action, result, limitation in manual:
    rows.append(dict(feature=feature, action=action, test_result=result, remaining_limitation=limitation,
        evidence="PHASE7E-STABILIZATION.md", verification_type="remaining release gate"))
with (output / "acceptance-matrix.csv").open("w", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=["feature", "action", "test_result", "remaining_limitation", "verification_type", "evidence"])
    writer.writeheader(); writer.writerows(rows)
summary = dict(rows=len(rows), backend_xml_cases=len(cases), source_controls=source["controls"], source_files=source["files"],
    frontend_commands=len(frontend), recommendation="NO-GO", all_actions_verified=False,
    failures=sum(row["test_result"] == "FAIL" for row in rows), skips=sum(row["test_result"] == "SKIP" for row in rows))
(output / "acceptance-summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
