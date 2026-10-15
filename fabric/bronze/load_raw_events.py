# FABRIC NOTEBOOK SOURCE (PySpark); requires a running Fabric Lakehouse notebook.
# Attach the *bronze_lh* schema-enabled Lakehouse as the default lakehouse.
# Upload the CSV produced by `medallion-x demo` into OneLake Files first.
# Set INPUT_CSV to the corresponding abfss:// path in Fabric.
# Not executable using the local Python reference simulator.
from pyspark.sql.types import StructType, StructField, StringType
from pyspark.sql import functions as F

INPUT_CSV = "abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<bronze_lh>.Lakehouse/Files/incoming/bronze_payment_events.csv"
TARGET_TABLE = "dbo.raw_payment_events"

if "<workspace>" in INPUT_CSV or "<bronze_lh>" in INPUT_CSV:
    raise RuntimeError("Replace INPUT_CSV placeholders with your real OneLake path")

fields = ["event_id", "transaction_id", "event_at", "ingested_at", "status",
          "amount_cents", "gross_amount_cents", "currency", "payload_schema_version", "customer_id"]
schema = StructType([StructField(name, StringType(), True) for name in fields])
raw = spark.read.option("header", True).schema(schema).csv(INPUT_CSV)
if raw.count() == 0:
    raise ValueError("Empty Bronze feed, refusing to write")
# Raw append intentionally preserves duplicates, bad contracts, and original payloads.
# In a production ingest add a file_id/batch_id and enforce batch-level replay idempotence.
raw.write.format("delta").mode("append").saveAsTable(TARGET_TABLE)
print(f"Appended {raw.count()} raw events into {TARGET_TABLE}")
