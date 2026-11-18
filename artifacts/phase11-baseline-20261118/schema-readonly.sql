\set ON_ERROR_STOP on
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
DO $$ BEGIN
 IF current_setting('transaction_read_only') <> 'on' OR current_database() <> 'apexretail_pos' THEN
  RAISE EXCEPTION 'Read-only identity guard failed';
 END IF;
END $$;
SELECT current_database() AS database, current_setting('transaction_read_only') AS read_only, current_setting('server_version') AS server_version;
SELECT version_num FROM alembic_version;
SELECT count(*) AS public_tables FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';
SELECT contype, count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace GROUP BY contype ORDER BY contype;
ROLLBACK;
