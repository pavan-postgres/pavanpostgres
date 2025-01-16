-- Set the necessary PostgreSQL settings for logical replication
ALTER SYSTEM SET wal_level = 'logical';
ALTER SYSTEM SET max_replication_slots = 4;
ALTER SYSTEM SET max_wal_senders = 8;

-- Reload configuration after altering the system settings. Additionally master instance also will be rebooted for above static parameters using entrypoint
SELECT pg_reload_conf();
