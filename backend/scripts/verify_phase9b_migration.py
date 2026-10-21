"""Continue the existing rehearsal; never reset/create a database or touch production."""
import json
from pathlib import Path
import os
import subprocess
import sys
from verify_phase8_migration import CLONE, TESTS, ROOT, query, historical


def migrate(database, target):
    if database not in [CLONE, *TESTS] or target not in ('p9a_fiscal_preparation', 'p9b_fiscal_protocol'):
        raise RuntimeError('Unapproved migration target or database')
    if query(database, 'SELECT current_database()') != database:
        raise RuntimeError('Wrong database identity')
    if database == CLONE and query(database, "SELECT has_database_privilege('apex_user', current_database(), 'CONNECT')") != 'f':
        raise RuntimeError('Clone must remain application-inaccessible')
    env = dict(os.environ, JWT_SECRET='disposable-phase9-only',
               DATABASE_URL=f'postgresql+asyncpg://postgres@/{database}?host=/var/run/postgresql')
    subprocess.run([sys.executable, '-m', 'alembic', 'downgrade' if target == 'p9a_fiscal_preparation' else 'upgrade', target], cwd=ROOT, env=env, check=True)


def main():
    result = {'production_accessed': False, 'created_databases': False, 'clone': CLONE, 'before': historical(), 'steps': []}
    for target in ('p9b_fiscal_protocol', 'p9a_fiscal_preparation', 'p9b_fiscal_protocol'):
        migrate(CLONE, target)
        result['steps'].append({'revision': query(CLONE, 'SELECT version_num FROM alembic_version'), 'historical': historical()})
    for database in TESTS:
        migrate(database, 'p9b_fiscal_protocol')
    Path('/tmp/phase9b-migration-results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
