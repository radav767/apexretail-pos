"""Read-only row/ledger/schema preservation controls. Results must remain private."""
import hashlib,json
from psycopg2 import sql

class PreservationError(RuntimeError):pass

def capture(connection,columns=None,app_role='apex_user'):
    if not connection.readonly:raise PreservationError('Read-only connection required')
    with connection.cursor() as c:
        c.execute('SHOW transaction_read_only')
        if c.fetchone()[0]!='on':raise PreservationError('Read-only transaction required')
        c.execute("SELECT current_database(),current_user,current_setting('server_version_num')")
        database,user,version=c.fetchone()
        if columns is None:
            c.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name<>'alembic_version' ORDER BY table_name,ordinal_position")
            columns={}
            for table,column in c:columns.setdefault(table,[]).append(column)
        tables={};totals={}
        for table,names in sorted(columns.items()):
            fields=sql.SQL(',').join(map(sql.Identifier,names))
            query=sql.SQL('SELECT row_to_json(t)::text FROM (SELECT {} FROM public.{}) t ORDER BY row_to_json(t)::text COLLATE "C"').format(fields,sql.Identifier(table))
            h=hashlib.sha256();count=0
            # Named cursor avoids materializing business rows in the runner.
            with connection.cursor(name='phase11_'+hashlib.sha256(table.encode()).hexdigest()[:16]) as rows:
                rows.itersize=1000;rows.execute(query)
                for row in rows:h.update(row[0].encode());h.update(b'\n');count+=1
            tables[table]={'count':count,'sha256':h.hexdigest()}
            c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND data_type IN ('smallint','integer','bigint','numeric') ORDER BY ordinal_position",(table,))
            numeric=[row[0] for row in c if row[0] in names]
            if numeric:
                groups=[n for n in names if n=='company_id' or n.endswith('currency_code') or n=='currency_code']
                fields=[sql.Identifier(n) for n in groups]+[sql.SQL('sum({})::text').format(sql.Identifier(n)) for n in numeric]
                query=sql.SQL('SELECT {} FROM public.{}').format(sql.SQL(',').join(fields),sql.Identifier(table))
                if groups:
                    group=sql.SQL(',').join(map(sql.Identifier,groups));query+=sql.SQL(' GROUP BY {} ORDER BY {}').format(group,group)
                c.execute(query);totals[table]={'groups':groups,'numeric':numeric,'rows':[[str(v) if v is not None else None for v in row] for row in c]}
        c.execute("SELECT c.relname,pg_get_userbyid(c.relowner),c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND relkind='r' ORDER BY c.relname")
        owners={row[0]:{'owner':row[1],'acl':row[2]} for row in c if row[0] in columns}
        c.execute("SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname")
        triggers=[list(row) for row in c]
        c.execute("SELECT p.oid::regprocedure::text,pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind='f' ORDER BY p.oid::regprocedure::text")
        functions={name:hashlib.sha256(body.encode()).hexdigest() for name,body in c}
        c.execute("SELECT count(*) FROM pg_index i JOIN pg_class r ON r.oid=i.indrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname='public' AND (NOT i.indisvalid OR NOT i.indisready)")
        if c.fetchone()[0]:raise PreservationError('Invalid/unready index requires review')
        c.execute("SELECT count(*) FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace WHERE n.nspname='public' AND NOT con.convalidated")
        if c.fetchone()[0]:raise PreservationError('Unvalidated constraint requires review')
        c.execute('SELECT version_num FROM alembic_version');revision=c.fetchone()[0]
        c.execute("SELECT count(*) FROM cashier_shifts WHERE status='open'");shifts=c.fetchone()[0]
        c.execute('SELECT count(*) FROM company_settings WHERE shift_enforcement_enabled AND NOT deleted');enforcement=c.fetchone()[0]
        c.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)",(app_role,));role_exists=c.fetchone()[0]
        role=None
        if role_exists:
            c.execute("SELECT has_database_privilege(%s,current_database(),'CONNECT'),has_schema_privilege(%s,'public','CREATE')",(app_role,app_role));connect,create=c.fetchone();role={'connect':connect,'schema_create':create}
    return {'database':database,'user':user,'server_version_num':version,'revision':revision,'columns':columns,'tables':tables,'numeric_controls':totals,'ownership':owners,'triggers':triggers,'functions':functions,'open_shifts':shifts,'shift_enforcement':enforcement,'app_role':role}

def compare(before,after):
    for field in ['tables','numeric_controls','ownership','open_shifts','shift_enforcement','app_role']:
        if before[field]!=after[field]:raise PreservationError('Preservation mismatch: '+field)
    # Additive migrations can add guards, but must preserve every existing guard.
    if not all(trigger in after['triggers'] for trigger in before['triggers']):
        raise PreservationError('Original database trigger changed/removed; explicit review required')

    if any(after['functions'].get(name)!=digest for name,digest in before['functions'].items()):
        raise PreservationError('Original database function changed/removed; explicit review required')
