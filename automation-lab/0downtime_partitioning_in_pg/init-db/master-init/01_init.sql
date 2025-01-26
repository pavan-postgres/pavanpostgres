-- create replica user
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'replica_user') THEN
        CREATE ROLE replica_user WITH LOGIN REPLICATION PASSWORD 'postgres';
    END IF;
END;
$$;



-- Create database if it doesn't exist (for safety)
 SELECT 'CREATE DATABASE testDB' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'testDB')\gexec ;

-- Connect to testDB (this is necessary because we might be running in the 'postgres' DB by default)
\c testDB

-- Create the orders table if it doesn't exist
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    order_date DATE NOT NULL
);

-- grant privilege on orders table to replica_user
GRANT SELECT ON TABLE orders to replica_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO replica_user;
