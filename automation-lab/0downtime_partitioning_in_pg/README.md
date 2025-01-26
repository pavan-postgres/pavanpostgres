# Online Partitioning with Replication Support (Zero Downtime ~ Under 10 Seconds)

## Implementation

  ### git clone the repo
    git clone url:0downtime_partitioning_in_pg

  ### switch to the working directory
    cd pavanpostgres/scripts/0downtime_partitioning_in_pg/

  ### issue docker build
    docker-compose up --build

  ### check for the instances launched
    docker ps (sample output)

    CONTAINER ID   IMAGE                        COMMAND                  CREATED        STATUS                                  PORTS                                       NAMES
    366dcce61137   postgres                     "docker-entrypoint.s…"   13 hours ago   Up 13 hours                             5432/tcp                                    p_pg_replica
    0df68c6b0039   postgres-pg-partman:latest   "docker-entrypoint.s…"   13 hours ago   Up 13 hours (healthy)                   5432/tcp                                    p_pg_master
    
  ## Publisher Validation: veriy the existance of the publication / data in orders table / replication slot existence :

  ### connect to publisher
    docker exec -it pg_master bash
    su postgres
    psql -d testDB -U master_user

      testDB=# \dRp
                                        List of publications
        Name        |    Owner    | All tables | Inserts | Updates | Deletes | Truncates | Via root
    --------------------+-------------+------------+---------+---------+---------+-----------+----------
     orders_publication | master_user | f          | t       | t       | t       | t         | f
    (1 row)

    testDB=# select * from orders;
     id | product_name | quantity | order_date
    ----+--------------+----------+------------
      1 | Product BC   |        6 | 2025-01-03
      2 | Product CD   |       11 | 2024-12-24
      3 | Product DE   |       16 | 2024-12-14
      4 | Product EF   |       21 | 2024-12-04
      5 | Product FG   |       26 | 2024-11-24
      6 | Product GH   |       31 | 2024-11-14
      7 | Product HI   |       36 | 2024-11-04
      8 | Product IJ   |       41 | 2024-10-25
      9 | Product JK   |       46 | 2024-10-15
     10 | Product KL   |       51 | 2024-10-05
     11 | Product MN   |       50 | 2024-11-05
     12 | Product LM   |       50 | 2024-11-05
     13 | Product NO   |       50 | 2024-11-05
    (13 rows)

    testDB=# SELECT now()::timestamp(0), database ,slot_name, pg_current_wal_lsn(), restart_lsn, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(),restart_lsn)) as replicationSlotLag, active from pg_replication_slots;
             now         | database |    slot_name    | pg_current_wal_lsn | restart_lsn | replicationslotlag | active
    ---------------------+----------+-----------------+--------------------+-------------+--------------------+--------
     2025-01-16 18:44:44 | testDB   | my_subscription | 0/19637B8          | 0/1963780   | 56 bytes           | t
    (1 row)
    
    testDB=# \d orders
                               Table "public.orders"
        Column    |  Type   | Collation | Nullable |              Default
    --------------+---------+-----------+----------+------------------------------------
     id           | integer |           | not null | nextval('orders_id_seq'::regclass)
     product_name | text    |           | not null |
     quantity     | integer |           | not null |
     order_date   | date    |           | not null |
    Indexes:
        "orders_pkey" PRIMARY KEY, btree (id)
    Publications:
        "orders_publication"
  
  ## Subscriber Validation: Check for incoming data while inserting in publisher and existence of subscription

  ### connect to subscriber
    docker exec -it pg_replica bash
    su postgres
    psql -d testDB -U replica_user

      testDB=# \dRs
                          List of subscriptions
          Name       |    Owner     | Enabled |     Publication
    -----------------+--------------+---------+----------------------
     my_subscription | replica_user | t       | {orders_publication}
    (1 row)
    
    testDB=# select * from orders;
     id | product_name | quantity | order_date
    ----+--------------+----------+------------
      1 | Product BC   |        6 | 2025-01-03
      2 | Product CD   |       11 | 2024-12-24
      3 | Product DE   |       16 | 2024-12-14
      4 | Product EF   |       21 | 2024-12-04
      5 | Product FG   |       26 | 2024-11-24
      6 | Product GH   |       31 | 2024-11-14
      7 | Product HI   |       36 | 2024-11-04
      8 | Product IJ   |       41 | 2024-10-25
      9 | Product JK   |       46 | 2024-10-15
     10 | Product KL   |       51 | 2024-10-05
     11 | Product MN   |       50 | 2024-11-05
     12 | Product LM   |       50 | 2024-11-05
     13 | Product NO   |       50 | 2024-11-05
    (13 rows)
    
    testDB=# \d orders
                               Table "public.orders"
        Column    |  Type   | Collation | Nullable |              Default
    --------------+---------+-----------+----------+------------------------------------
     id           | integer |           | not null | nextval('orders_id_seq'::regclass)
     product_name | text    |           | not null |
     quantity     | integer |           | not null |
     order_date   | date    |           | not null |
    Indexes:
        "orders_pkey" PRIMARY KEY, btree (id)
          

  ## Replication is up and running in less than a minute! Now lets try to partition the unpartitioned table online.!😊

  ### Connect to master / publisher and execute the below steps in transaction
  
     begin transaction;
    
     alter table orders drop constraint orders_pkey ;
    
     alter table orders add primary key (id,order_date);
    
     ALTER TABLE orders RENAME TO orders_unpartitioned;
    
     CREATE TABLE IF NOT EXISTS orders
      (
         id           SERIAL ,
         product_name TEXT NOT NULL,
         quantity     INTEGER NOT NULL,
         order_date   DATE NOT NULL,
         PRIMARY KEY (id, order_date)
      ) PARTITION BY RANGE(order_date);
    
     CREATE TABLE orders_p202502 PARTITION OF orders FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
    
     CREATE TABLE orders_default PARTITION OF orders DEFAULT;
    
     ALTER TABLE orders ATTACH PARTITION orders_unpartitioned FOR VALUES FROM ('2024-09-27') TO ('2025-01-07');
    
     ALTER PUBLICATION orders_publication ADD TABLE orders_default ;
    
     grant select on all tables in schema public to replica_user ;
    
     ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO replica_user;
    
     commit;

  #### Note: Upon committing the above transaction on the master, the orders table will successfully transition from non-partitioned to partitioned. However, this will break replication. 
  #### To resolve this(follow below), ensure that the subscriber's structure is synchronized with the master.

  ### Connect to replica / subscriber and execute the below steps in transaction

     begin transaction;
    
     alter table orders drop constraint orders_pkey ;
    
     alter table orders add primary key (id,order_date);
    
     ALTER TABLE orders RENAME TO orders_unpartitioned;
    
     CREATE TABLE IF NOT EXISTS orders
      (
         id           SERIAL ,
         product_name TEXT NOT NULL,
         quantity     INTEGER NOT NULL,
         order_date   DATE NOT NULL,
         PRIMARY KEY (id, order_date)
      ) PARTITION BY RANGE(order_date);
    
     CREATE TABLE orders_p202502 PARTITION OF orders FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
    
     CREATE TABLE orders_default PARTITION OF orders DEFAULT;
    
     ALTER TABLE orders ATTACH PARTITION orders_unpartitioned FOR VALUES FROM ('2024-09-27') TO ('2025-01-07');
    
     ALTER PUBLICATION orders_publication ADD TABLE orders_default ;
    
     commit;

  ## This fixes the replication too !!!! Validate by inserting a row on publisher it should be reflecting on subscriber. 

  #### NOTE: 
  ##### 1. This approach is to have 0(~very minimal) downtime for critical services. Later the data in the unpartitioned and default partitions can be moved to the respective partitions using pg_partman.
  ##### 2. In this setup only p_pg_master instance is configured with partman image in case if this image is required in replica the docker-compose file should be changed accordingly.
  



  
  
    
        
