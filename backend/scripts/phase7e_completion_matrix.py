"""Preserve explicit acceptance evidence; never infer all-button coverage."""
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[2]
output=root/"phase7e-evidence/completion/audit";output.mkdir(parents=True,exist_ok=True)
rows=[]
for case in ET.parse("/tmp/phase7e-completion-backend.xml").getroot().findall(".//testcase"):
    result="FAIL" if case.find("failure") is not None or case.find("error") is not None else "SKIP" if case.find("skipped") is not None else "PASS"
    rows.append(dict(feature=case.get("classname"),action=case.get("name"),result=result,type="automated backend unit/API/PostgreSQL test",limitation="Only the named behavior is verified; not every frontend action or physical device.",evidence="backend-regression.xml"))
for test in json.loads((root/"phase7e-evidence/completion/frontend/frontend-test-results.json").read_text()):
    rows.append(dict(feature=test["project"],action=test["script"],result=test["status"],type="frontend regression/lint/build command",limitation="Some checks are source assertions; not authenticated end-to-end UI proof.",evidence=f"frontend/{test['project']}-{test['script'].replace(':','-')}.log"))
for check in json.loads((root/"phase7e-evidence/completion/preview/checks.json").read_text())["checks"]:
    rows.append(dict(feature=check["feature"],action=f"{check['device']}: {check['action']}",result="PASS",type="actual React component, synthetic adapter",limitation="No physical hardware, production data or complete login shell.",evidence="preview/checks.json"))
inventory=json.loads((output/"ui-action-inventory.json").read_text())
for control in inventory["rows"]:
    rows.append(dict(feature=control["feature"],action=control["action"],result="PENDING authenticated E2E",type="source control/template inventory",limitation="Do not mark PASS from source connectivity, build success or screenshots alone.",evidence=control["source"]))
for feature,action,limitation in [
    ("Permissions","Every legacy form/action under every role, branch and device","126 granular denial subtests and targeted route tests pass; exhaustive authenticated browser permutations remain pending."),
    ("Restaurant offline","Physical cold restart, PIN restore, backgrounding and reconnect","Browser/outbox/server retry evidence passes. New draft creation without a loaded profile and offline payment/KOT/merge remain outside supported offline recovery."),
    ("Android","Installed APK login, sale, inventory, navigation, offline and printing","ADB lists no devices. Native source unchanged; no APK built or installed."),
    ("Printing","Bluetooth, USB, LAN, receipt, KOT, stations, routing, 58mm/80mm","No Android device or USB printer; no Bluetooth adapter or test LAN destination. Software queue/routing/source tests do not prove physical delivery."),
    ("Production","Fresh backup, live data and protected migration runner review","Only the verified October 16 backup and isolated restored clone were inspected. No production connection."),
]:rows.append(dict(feature=feature,action=action,result="PENDING",type="manual/release acceptance gate",limitation=limitation,evidence="PHASE7E-COMPLETION.md"))
with (output/"acceptance-matrix.csv").open("w",newline="") as f:
    writer=csv.DictWriter(f,fieldnames=["feature","action","result","limitation","type","evidence"]);writer.writeheader();writer.writerows(rows)
summary={"rows":len(rows),"sourceControls":inventory["controls"],"sourceFiles":inventory["files"],"automatedFailures":sum(r["result"]=="FAIL" for r in rows),"automatedSkips":sum(r["result"]=="SKIP" for r in rows),"allActionsVerified":False,"status":"PENDING_ACCEPTANCE_NOT_READY"}
(output/"acceptance-summary.json").write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
