"""Rehearse only on existing isolated Phase 7E fixtures and archived clone."""
import json
from pathlib import Path
import os
import subprocess
import sys
from verify_phase8_migration import CLONE, TESTS, ROOT, query, historical


def migrate(database, target):
    if database not in [CLONE, *TESTS]:
        raise RuntimeError('Non-disposable database refused')
    if query(database, 'SELECT current_database()') != database:
        raise RuntimeError('Wrong database identity')
    if query(database, "SELECT has_database_privilege('apex_user', current_database(), 'CONNECT')") != 'f' and database == CLONE:
        raise RuntimeError('Archived clone must remain application-inaccessible')
    env = dict(os.environ, JWT_SECRET='disposable-phase9-only',
               DATABASE_URL=f'postgresql+asyncpg://postgres@/{database}?host=/var/run/postgresql')
    direction = 'downgrade' if target == 'p8a_commercial_billing' else 'upgrade'
    subprocess.run([sys.executable, '-m', 'alembic', direction, target], cwd=ROOT, env=env, check=True)


def main():
    result = {'production_accessed': False, 'created_databases': False, 'clone': CLONE,
              'before': historical(), 'steps': []}
    for target in ('p9a_fiscal_preparation', 'p8a_commercial_billing', 'p9a_fiscal_preparation'):
        migrate(CLONE, target)
        result['steps'].append({'revision': query(CLONE, 'SELECT version_num FROM alembic_version'), 'historical': historical()})
    for database in TESTS:
        migrate(database, 'p9a_fiscal_preparation')
    Path('/tmp/phase9-migration-results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
