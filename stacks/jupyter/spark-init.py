import os
try:
    from IPython import get_ipython
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
    _spark = builder.getOrCreate()
    _sc = _spark.sparkContext
    # Inject into notebook namespace so spark/sc are available in cells
    _ip = get_ipython()
    _ip.user_ns["spark"] = _spark
    _ip.user_ns["sc"] = _sc
    print(f"SparkSession ready (master: {master})")
    del _spark, _sc, _ip
except Exception as e:
    print(f"Spark not available: {e}")
