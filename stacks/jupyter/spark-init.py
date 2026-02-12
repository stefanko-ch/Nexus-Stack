import os
try:
    from pyspark.sql import SparkSession
    master = os.environ.get("SPARK_MASTER", "local[*]")
    builder = SparkSession.builder.master(master).appName("Jupyter Notebook")
    endpoint = os.environ.get("SPARK_HADOOP_fs_s3a_endpoint", "")
    if endpoint:
        builder = builder \
            .config("spark.hadoop.fs.s3a.endpoint", endpoint) \
            .config("spark.hadoop.fs.s3a.access.key", os.environ.get("SPARK_HADOOP_fs_s3a_access_key", "")) \
            .config("spark.hadoop.fs.s3a.secret.key", os.environ.get("SPARK_HADOOP_fs_s3a_secret_key", "")) \
            .config("spark.hadoop.fs.s3a.path.style.access", "true") \
            .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    spark = builder.getOrCreate()
    sc = spark.sparkContext
    print(f"SparkSession ready (master: {master})")
except Exception as e:
    print(f"Spark not available: {e}")
