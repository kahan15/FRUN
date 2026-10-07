-- Administrator-only, NEW DEDICATED database. Never apply to an existing app DB.
-- This creates roles with no password. Configure distinct secrets separately.
BEGIN;
DO $$ BEGIN
  IF to_regclass('public.users') IS NOT NULL
     OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('territory_runtime','territory_migrator')) THEN
    RAISE EXCEPTION 'Fresh database and unused role names required';
  END IF;
END $$;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE ROLE territory_migrator LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE territory_runtime LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
DO $$ BEGIN
  EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO territory_migrator, territory_runtime', current_database());
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO territory_migrator;
GRANT USAGE ON SCHEMA public TO territory_runtime;
-- Future application objects get no implicit PUBLIC access or runtime writes.
ALTER DEFAULT PRIVILEGES FOR ROLE territory_migrator IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE territory_migrator IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
COMMIT;
