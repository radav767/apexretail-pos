"""Refresh an uncommitted development migration function in ONLY its test DB."""
import os,ast,asyncio
from pathlib import Path
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
url=make_url(os.environ['DATABASE_URL'])
assert os.environ['APP_ENV']=='test' and url.database=='apexretail_phase7c_test_phase7e' and not url.host and url.query['host']=='/tmp/apex-phase11-postgres-auOybQ' and url.query['port']=='55441'
source=Path('/tmp/apexpos-phase11/backend/migrations/versions/p11p_stock_movement_revisions.py').read_text()
tree=ast.parse(source)
statement=next(node.args[0].value for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='execute' and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str) and node.args[0].value.startswith('CREATE FUNCTION bump_stock_revision'))
async def main():
 engine=create_async_engine(url)
 async with engine.begin() as db:await db.execute(text(statement.replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)))
 await engine.dispose();print('Owned prototype test function refreshed from the final uncommitted migration; no shared branch revision lock')
asyncio.run(main())
