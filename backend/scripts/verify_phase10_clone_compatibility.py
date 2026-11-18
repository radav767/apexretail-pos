"""Read-only compatibility checks on the exact freshly restored clone only.

Does not accept production URLs, log user data, authenticate to live endpoints,
or write any business records. Synthetic JWT signing is confined to this process.
"""
import asyncio,json,os,sys
from pathlib import Path
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession
from sqlalchemy.engine import make_url

DATABASE='apexretail_phase10_fresh_20261021t072213'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def compatibility_url(value):
    """Require an explicit clone destination before importing application config."""
    if not value:
        raise RuntimeError('PHASE10_COMPATIBILITY_DATABASE_URL is required')
    url=make_url(value)
    if url.drivername!='postgresql+asyncpg' or url.database!=DATABASE:
        raise RuntimeError('Only the named disposable compatibility clone is allowed')
    if url.host or not str(url.query.get('host','')).startswith('/'):
        raise RuntimeError('An explicit local PostgreSQL socket is required')
    return value

async def main():
    URL=compatibility_url(os.environ.get('PHASE10_COMPATIBILITY_DATABASE_URL'))
    os.environ['DATABASE_URL']=URL
    os.environ['JWT_SECRET']='isolated-phase10-compatibility-not-production'
    import httpx
    from app.main import app
    from app.db.session import get_db
    from app.db.base import Base
    from app.auth.security import create_access_token
    from app.models import User
    engine=create_async_engine(URL);checks=[];failures=[]
    contracts={'checked':False}
    schema_file=Path(os.environ.get('PHASE10_COMPATIBILITY_SCHEMA','/tmp/phase10-production-openapi.json'))
    if schema_file.exists():
        old=json.loads(schema_file.read_text());new=app.openapi();missing=[];required=[];operations=0
        def fields(document,operation):
            schema=operation.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema',{})
            if '$ref' in schema:schema=document.get('components',{}).get('schemas',{}).get(schema['$ref'].split('/')[-1],{})
            return set(schema.get('required',[]))
        for path,methods in old['paths'].items():
            for method,operation in methods.items():
                if method not in ('get','post','patch','put','delete','head','options'):continue
                operations+=1;candidate=new['paths'].get(path,{}).get(method)
                if not candidate:missing.append({'path':path,'method':method});continue
                extra=fields(new,candidate)-fields(old,operation)
                old_parameters={(p.get('in'),p['name']) for p in operation.get('parameters',[]) if p.get('required')}
                new_parameters={(p.get('in'),p['name']) for p in candidate.get('parameters',[]) if p.get('required')}
                if extra or new_parameters-old_parameters:required.append({'path':path,'method':method,'body_fields':sorted(extra),'parameters':sorted(new_parameters-old_parameters)})
        contracts={'checked':True,'production_operations':operations,'missing_operations':missing,'new_required_inputs':required,
            'scope':'Route/method presence and top-level required JSON/query/path inputs only; not proof of full semantic or device compatibility'}
        if missing or required:failures.append({'scope':'contract_comparison','details':contracts})
    async with engine.connect() as conn:
        outer=await conn.begin()
        await conn.execute(text('SET TRANSACTION READ ONLY'))
        if (await conn.execute(text('SHOW transaction_read_only'))).scalar_one()!='on':
            raise RuntimeError('Read-only transaction was not established')
        identity=(await conn.execute(text('SELECT current_database()'))).scalar_one()
        if identity!=DATABASE:raise RuntimeError('Wrong database')
        if (await conn.execute(text("SELECT has_database_privilege('apex_user',current_database(),'CONNECT')"))).scalar_one():raise RuntimeError('Clone must remain application-inaccessible')
        await conn.execute(text('SET LOCAL ROLE apex_user'))
        for table in Base.metadata.sorted_tables:
            try:
                async with conn.begin_nested():await conn.execute(table.select().limit(0))
                checks.append({'scope':'runtime_schema','table':table.name,'passed':True})
            except Exception as e:failures.append({'scope':'runtime_schema','table':table.name,'error_type':type(e).__name__})
        owners=(await conn.execute(select(User.id,User.email,User.company_id,User.session_version).where(User.role=='owner',User.active==True,User.deleted==False))).all()
        if not owners:raise RuntimeError('Compatibility checks require owner fixtures')
        async def override():
            async with AsyncSession(bind=conn,expire_on_commit=False,join_transaction_mode='create_savepoint') as session:yield session
        app.dependency_overrides[get_db]=override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='http://isolated-clone.test') as client:
                for uid,email,company,session_version in owners:
                    token=create_access_token(str(uid),email,session_version=session_version)
                    paths=[('/api/products/{company}',200),('/api/products/variants/{company}',200),('/api/inventory/overview/{company}',200),
                           ('/api/sales/{company}',200),('/api/employees/{company}',200),('/api/shifts/company/{company}',200),
                           ('/api/currencies/{company}',200),('/api/credit/{company}/receivables',200),('/api/credit/{company}/settlements',200),
                           ('/api/expenses/{company}',200),('/api/subscriptions/access/{company}',200),
                           ('/api/reports/financial-summary/{company}?date_from=2026-01-01&date_to=2026-12-31',200),
                           ('/api/platform/dashboard',401),('/api/platform/administrators',401)]
                    for path,expected in paths:
                        response=await client.get(path.format(company=company),headers={'Authorization':'Bearer '+token})
                        result={'scope':'owner_readonly_api','endpoint':path,'status':response.status_code,'expected':expected,'passed':response.status_code==expected}
                        checks.append(result)
                        if not result['passed']:failures.append(result)
                    other=next((row.company_id for row in owners if row.company_id!=company),None)
                    if other:
                        response=await client.get(f'/api/products/{other}',headers={'Authorization':'Bearer '+token})
                        result={'scope':'cross_business_denial','status':response.status_code,'expected':403,'passed':response.status_code==403};checks.append(result)
                        if not result['passed']:failures.append(result)
                for path in ['/api/platform/dashboard','/api/platform/devices','/api/platform/settings']:
                    response=await client.get(path);result={'scope':'anonymous_api','endpoint':path,'status':response.status_code,'passed':response.status_code==401};checks.append(result)
                    if not result['passed']:failures.append(result)
        finally:app.dependency_overrides.clear()
        await outer.rollback()
    await engine.dispose()
    out=Path(os.environ.get('PHASE10_COMPATIBILITY_OUTPUT','/tmp/phase10-clone-compatibility.json'))
    out.write_text(json.dumps({'database':DATABASE,'production_accessed':False,'business_writes':False,'owners_checked':len(owners),'contracts':contracts,'checks':checks,'failures':failures},indent=2));out.chmod(0o600)
    print(json.dumps({'checks':len(checks),'owners_checked':len(owners),'contracts':contracts,'failures':failures,'evidence':str(out)}))
    if failures:raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
