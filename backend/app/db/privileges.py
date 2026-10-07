"""Fail closed on powerful production runtime connections (also used by workers)."""

RUNTIME_GUARD_SQL = """
SELECT current_user = session_user
 AND NOT EXISTS (
   SELECT 1 FROM pg_roles WHERE rolname=current_user
     AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
 AND NOT EXISTS (
   SELECT 1 FROM pg_roles WHERE rolname<>current_user
     AND pg_has_role(current_user, oid, 'MEMBER'))
 AND NOT has_database_privilege(current_database(), 'CREATE')
 AND NOT has_database_privilege(current_database(), 'TEMP')
 AND NOT EXISTS (
   SELECT 1 FROM pg_namespace WHERE nspname !~ '^pg_temp_'
     AND has_schema_privilege(oid, 'CREATE'))
 AND NOT EXISTS (
   SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND
     (pg_get_userbyid(c.relowner)=current_user OR
      (c.relkind IN ('r','p','v','m','f') AND
       (has_table_privilege(c.oid, 'TRUNCATE,REFERENCES,TRIGGER') OR
        has_table_privilege(c.oid, 'SELECT WITH GRANT OPTION,INSERT WITH GRANT OPTION,UPDATE WITH GRANT OPTION,DELETE WITH GRANT OPTION')))))
 AND NOT EXISTS (
   SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname='public' AND pg_get_userbyid(p.proowner)=current_user)
"""


def enforce_runtime_privileges(connection, _record):
    with connection.cursor() as cursor:
        cursor.execute(RUNTIME_GUARD_SQL)
        allowed = cursor.fetchone()[0]
    connection.rollback()
    if not allowed:
        raise RuntimeError("Production database runtime privileges are unsafe")
