# 1 min Logical Replication Setup using docker

## Implementation

  ## git clone the repo
    git clone url:1min_pg_logicalreplication_setup

  ## switch to the working directory
    cd pavanpostgres/scripts/1min_pg_logicalreplication_setup/

  ## issue docker build
    docker-compose up --build

  ## check for the instances launched
    docker ps (sample output)

    CONTAINER ID   IMAGE                        COMMAND                  CREATED        STATUS                          PORTS                                       NAMES
    5df027ea771a   postgres                     "docker-entrypoint.s…"   2 days ago     Up 2 days                       5432/tcp                                    pg_replica
    1a4efb8ee438   postgres                     "docker-entrypoint.s…"   2 days ago     Up 2 days (healthy)             5432/tcp                                    pg_master
    
  
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
    
    testDB=#
  
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

  ## Replication is up and running in less than a minute! Start experiencing, and taking it to the next level.!😊
  
    
        
         
