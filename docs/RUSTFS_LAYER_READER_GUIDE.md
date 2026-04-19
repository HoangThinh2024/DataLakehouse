# RustFS Layer Reader – Developer Guide

Quick reference for reading and writing data from RustFS lake layers.

## Overview

The `mage/utils/rustfs_layer_reader.py` module provides utilities to read data from RustFS Bronze, Silver, and Gold layers. Use this for:

- ✓ Custom transformations reading from RustFS
- ✓ Data validation and quality checks
- ✓ Ad-hoc analytics queries
- ✓ Reprocessing historical data
- ✓ Debugging and troubleshooting

## Usage

### Basic: Read Latest Data

```python
from utils.rustfs_layer_reader import read_latest_silver, read_all_gold

# Read latest Silver (cleaned data)
silver_df = read_latest_silver()
print(f"Loaded {len(silver_df)} rows from Silver layer")

# Read all Gold aggregations
gold = read_all_gold()
print(f"Daily: {len(gold['gold_daily'])} rows")
print(f"Weekly: {len(gold['gold_weekly'])} rows")
print(f"Monthly: {len(gold['gold_monthly'])} rows")
print(f"Yearly: {len(gold['gold_yearly'])} rows")
print(f"By Region: {len(gold['gold_region'])} rows")
print(f"By Category: {len(gold['gold_category'])} rows")
```

### Read Specific Date

```python
from utils.rustfs_layer_reader import read_latest_layer

# Read Silver from a specific date
silver_20250120 = read_latest_layer(
    bucket='silver',
    prefix='demo',
    date_str='2025-01-20'
)
```

### Available Functions

#### PostgreSQL Pipeline Data

```python
# Read Bronze (raw PostgreSQL extract)
from utils.rustfs_layer_reader import read_latest_bronze
bronze_df = read_latest_bronze()

# Read Silver (cleaned PostgreSQL data)
from utils.rustfs_layer_reader import read_latest_silver
silver_df = read_latest_silver()

# Read all Gold aggregations
from utils.rustfs_layer_reader import read_all_gold
gold = read_all_gold()

# Read specific Gold table
from utils.rustfs_layer_reader import (
    read_latest_gold_daily,
    read_latest_gold_weekly,
    read_latest_gold_monthly,
    read_latest_gold_yearly,
    read_latest_gold_region,
    read_latest_gold_category,
)
daily = read_latest_gold_daily()
weekly = read_latest_gold_weekly()
monthly = read_latest_gold_monthly()
yearly = read_latest_gold_yearly()
region = read_latest_gold_region()
category = read_latest_gold_category()
```

#### CSV Pipeline Data

```python
# Read cleaned CSV upload data
from utils.rustfs_layer_reader import read_latest_csv_silver
csv_df = read_latest_csv_silver()
```

### Advanced: Generic Layer Reader

```python
from utils.rustfs_layer_reader import read_latest_layer, list_layer_partitions

# List all available partitions (dates)
partitions = list_layer_partitions('silver', 'demo')
# Returns: ['2025-01-20', '2025-01-19', '2025-01-18', ...]

# Read from specific partition
df = read_latest_layer('silver', 'demo', date_str='2025-01-20')

# Read from another layer (e.g., custom layer)
df = read_latest_layer(
    bucket='gold',
    prefix='custom_aggregation'
)
```

## Configuration

The reader uses environment variables for RustFS connection:

```bash
# In docker-compose.yaml or .env
RUSTFS_ENDPOINT_URL=http://dlh-rustfs:9000
RUSTFS_ACCESS_KEY=rustfsadmin
RUSTFS_SECRET_KEY=rustfsadmin
RUSTFS_REGION=us-east-1

# Layer buckets and prefixes
RUSTFS_BRONZE_BUCKET=bronze
RUSTFS_BRONZE_PREFIX=demo
RUSTFS_SILVER_BUCKET=silver
RUSTFS_SILVER_PREFIX=demo
RUSTFS_GOLD_BUCKET=gold
RUSTFS_GOLD_PREFIX=demo_daily  # or demo_by_region, demo_by_category
```

## Common Patterns

### Pattern 1: Validate Data Quality

```python
from utils.rustfs_layer_reader import read_latest_silver

# Check for data quality issues
df = read_latest_silver()

# Verify no nulls in required fields
required_fields = ['id', 'name', 'value']
for field in required_fields:
    null_count = df[field].isna().sum()
    if null_count > 0:
        print(f"⚠️  {field}: {null_count} null values")

# Check value ranges
if (df['value'] < 0).any():
    print("⚠️  Negative values found in 'value' column")

print(f"✓ Quality check: {len(df)} rows validated")
```

### Pattern 2: Compare Versions

```python
from utils.rustfs_layer_reader import read_latest_layer

# Compare Silver from two dates
silver_today = read_latest_layer('silver', 'demo', '2025-01-20')
silver_yesterday = read_latest_layer('silver', 'demo', '2025-01-19')

# How many rows changed?
print(f"Today: {len(silver_today)} rows")
print(f"Yesterday: {len(silver_yesterday)} rows")
print(f"Delta: {len(silver_today) - len(silver_yesterday)} rows")

# Find new rows
old_ids = set(silver_yesterday['id'].dropna().unique())
new_rows = silver_today[~silver_today['id'].isin(old_ids)]
print(f"New rows: {len(new_rows)}")
```

### Pattern 3: Reprocess Yesterday's Data

```python
from utils.rustfs_layer_reader import read_latest_layer
import datetime as dt
import pandas as pd

# Get date from args or default to yesterday
yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()

# Read Bronze from that date
df = read_latest_layer('bronze', 'demo', yesterday)
print(f"Loaded {len(df)} rows from {yesterday}")

# Apply transformations
df['value'] = df['value'].fillna(0)
df['created_at'] = pd.to_datetime(df['created_at'])

# Write back to Silver (with new run_id)
# ... your export code here
```

### Pattern 4: Custom Aggregation

```python
from utils.rustfs_layer_reader import read_latest_silver
import pandas as pd

# Read Silver
df = read_latest_silver()

# Create custom aggregation
custom_agg = (
    df.groupby('region')
    .agg({
        'id': 'count',
        'value': ['sum', 'mean', 'min', 'max'],
    })
    .reset_index()
    .rename(columns={'id': 'order_count'})
)

print(f"Custom aggregation by region:\n{custom_agg}")

# Write to RustFS for archival
# ... your export code here
```

## Error Handling

```python
from utils.rustfs_layer_reader import read_latest_silver

try:
    df = read_latest_silver()
    if len(df) == 0:
        print("⚠️  No data found in Silver layer (first run?)")
    else:
        print(f"✓ Loaded {len(df)} rows")
except Exception as exc:
    print(f"✗ Error reading Silver: {exc}")
```

## Performance Considerations

1. **Parquet Format**: Files are highly compressed (5-10x smaller than CSV)
   - Read times: typically < 1s per partition on high-speed network

2. **Partition Pruning**: Always specify date range if possible
   ```python
   # ✓ Good: specific date
   df = read_latest_layer('silver', 'demo', '2025-01-20')
   
   # ⚠️  Slow: lists all dates to find latest
   df = read_latest_layer('silver', 'demo')
   ```

3. **Multiple Files Per Partition**: Automatically concatenates
   ```python
   # Combines all run_ids from that date into single DataFrame
   df = read_latest_layer('silver', 'demo', '2025-01-20')
   # Could be 100 parquet files merged into one df
   ```

## Integration with Mage Blocks

### In Transformers

```python
# transformer block
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.rustfs_layer_reader import read_latest_silver

def transform_data(data, *args, **kwargs):
    # Read from RustFS instead of using input
    df = read_latest_silver()
    
    # Transform...
    
    return df
```

### In Exporters

```python
# data_exporter block
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.rustfs_layer_reader import read_all_gold

def export_data(data, *args, **kwargs):
    # Read from RustFS (not from input)
    gold = read_all_gold()
    
    # Load to ClickHouse, Salesforce, etc...
    
    return {}
```

## Troubleshooting

### "Connection refused to RustFS"
```
Error: Cannot connect to  s3://bucket
```
- Check `RUSTFS_ENDPOINT_URL` is correct (default: `http://dlh-rustfs:9000`)
- Verify RustFS container is running: `docker compose ps dlh-rustfs`
- Check network connectivity

### "No data found"
```
[read_latest_layer] Combined 0 rows from 0 files
```
- Check partition exists: `aws s3 ls s3://silver/demo/ --recursive`
- Verify pipeline has run at least once
- Check date format (should be `YYYY-MM-DD`)

### "Credentials error"
```
botocore.exceptions.ClientError: An error occurred (SignatureDoesNotMatch)
```
- Verify `RUSTFS_ACCESS_KEY` and `RUSTFS_SECRET_KEY` are correct
- Check `.env` file matches docker-compose.yaml

## See Also

- [`load_to_clickhouse.py`](../mage/data_exporters/load_to_clickhouse.py) – Real-world example using `read_latest_silver` and `read_all_gold`
- [`verify_lakehouse_architecture.py`](../scripts/verify_lakehouse_architecture.py) – Validation script
- [Lakehouse Architecture Docs](../docs/LAKEHOUSE_ARCHITECTURE.md) – Full architecture overview
