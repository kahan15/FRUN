-- Run as the migration owner AFTER alembic upgrade head, in the dedicated DB.
-- Explicit allowlist: new tables require review here before the runtime uses them.
BEGIN;
REVOKE ALL ON users, sessions, friendships, runs, territories, contests, notifications,
  devices, push_deliveries, login_attempts, account_deletions, user_blocks,
  password_recoveries, accepted_friendships, alembic_version FROM territory_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  users, sessions, friendships, runs, territories, contests, notifications,
  devices, push_deliveries, login_attempts, account_deletions,
  user_blocks, password_recoveries TO territory_runtime;
GRANT SELECT ON accepted_friendships, alembic_version TO territory_runtime;
GRANT EXECUTE ON FUNCTION assert_no_territory_overlap() TO territory_runtime;
COMMIT;
