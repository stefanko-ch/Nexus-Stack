-- Runs once, when the data volume is first initialised, after the image
-- has created nexus-mysql (MYSQL_USER). Grants what Debezium's MySQL
-- connector needs to read the binlog; nexus-mysql already owns the
-- `nexus` database.
GRANT RELOAD, FLUSH_TABLES, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'nexus-mysql'@'%';
