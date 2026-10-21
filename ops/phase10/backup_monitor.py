"""UNINSTALLED read-only backup/recovery freshness check. No credentials/network.

Exit codes:0 healthy,1 warning,2 critical. Alert delivery/scheduling require
separate approval. Missing or invalid evidence is never treated as success.
"""
import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import backup_safety as safety
from backup_proposal import DATABASE, private


def status(root, now=None):
    safety.secure_ancestors(root)
    private(root, True)
    now = now or datetime.now(timezone.utc)
    transfers, restores = [], []
    rejected = 0
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        try:
            _, manifest = safety.package(folder)
            created = safety.instant(manifest['created_at'])
            receipt = safety.read_private_json(folder / 'offserver.json')
            verified = safety.instant(receipt['verified_at'])
            if (not created <= verified <= now or receipt.get('kind') != 'offserver-readback-v1'
                    or receipt.get('database') != DATABASE
                    or receipt.get('archive_sha256') != manifest['ciphertext_sha256']
                    or not re.fullmatch('[a-f0-9]{64}', str(receipt.get('config_sha256', '')))
                    or not re.fullmatch(manifest['ciphertext_sha256'] + '-[a-f0-9]{32}', str(receipt.get('object_id', '')))):
                raise ValueError('Invalid readback evidence')
            if receipt.get('provider') == 'google-drive':
                if (receipt.get('host') != 'www.googleapis.com'
                        or not re.fullmatch('[A-Za-z0-9_-]{10,200}', str(receipt.get('root_folder_id', '')))
                        or not re.fullmatch('[a-f0-9]{64}', str(receipt.get('oauth_binding_sha256', '')))):
                    raise ValueError('Invalid Drive evidence')
            elif receipt.get('provider') not in (None, 'sftp') or not re.fullmatch('SHA256:[A-Za-z0-9+/]{43}', str(receipt.get('host_key_fingerprint', ''))):
                raise ValueError('Invalid destination evidence')
            transfers.append(verified)
            # Daily readback is not a full restore. A recovery drill needs its own
            # complete baseline-bound proof and is monitored separately.
            try:
                safety.verified_package(folder, now)
                restores.append(safety.instant(safety.read_private_json(folder / 'restore.json')['verified_at']))
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                pass
        except (OSError, ValueError, RuntimeError, KeyError, TypeError):
            rejected += 1
    latest = max(transfers) if transfers else None
    recovered = max(restores) if restores else None
    age = (now - latest).total_seconds() if latest else None
    level = 'critical' if age is None or age >= 48 * 3600 else 'warning' if age >= 26 * 3600 else 'healthy'
    due = recovered is None or now - recovered >= timedelta(days=31)
    if due and level == 'healthy':
        level = 'warning'
    return {'mode': 'read-only-no-delivery', 'database': DATABASE, 'status': level,
            'last_verified_offserver_at': latest.isoformat() if latest else None,
            'last_full_recovery_at': recovered.isoformat() if recovered else None,
            'monthly_recovery_due': due, 'invalid_or_unverified_packages': rejected,
            'deleted': 0, 'network_requests': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = status(args.root)
        print(json.dumps(result, indent=2))
        raise SystemExit({'healthy': 0, 'warning': 1, 'critical': 2}[result['status']])
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        raise SystemExit('BACKUP STATUS CRITICAL: protected complete recovery evidence unavailable')
