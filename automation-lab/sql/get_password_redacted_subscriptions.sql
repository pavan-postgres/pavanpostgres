-- Query to get password less subscription info

SELECT subname,
       datname,
       pg_catalog.pg_get_userbyid(subowner) AS owner,
       regexp_replace(subconninfo, 'password=[^ ]+', 'password=****', 'g') AS subconninfo,
       subenabled AS enabled
FROM pg_subscription s
JOIN pg_database d ON s.subdbid = d.oid;


-- to add the same query in .psqlrc

\set sub_listn 'SELECT subname, datname, pg_catalog.pg_get_userbyid(subowner) AS owner, regexp_replace(subconninfo, ''password=[^ ]+'', ''password=****'', ''g'') AS subconninfo, subenabled AS enabled FROM pg_subscription s JOIN pg_database d ON s.subdbid = d.oid;'

