-- Connect to the 'testDB' on the replica
\c testDB

-- Create the subscription to the publication on the publisher
CREATE SUBSCRIPTION my_subscription CONNECTION 'host=p_pg_master dbname=testDB user=replica_user password=postgres' PUBLICATION orders_publication;
