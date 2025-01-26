-- Connect to the 'testDB' on the replica
\c testDB

-- Create the subscription to the publication on the publisher
CREATE SUBSCRIPTION orders_subscription CONNECTION 'host=pg_master dbname=testDB user=replica_user password=postgres' PUBLICATION orders_publication;
