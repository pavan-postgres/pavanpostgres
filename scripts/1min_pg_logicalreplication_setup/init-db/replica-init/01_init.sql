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
