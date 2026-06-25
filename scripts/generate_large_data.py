#!/usr/bin/env python3
import datetime
import io
import os
import random
import time
from pathlib import Path
import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[1]

def load_env():
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        print("❌ .env file not found. Run scripts/setup.sh first.")
        return False
    
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return True

def generate_data(num_rows=1000000):
    products = [
        ("Laptop Pro 15", "Electronics", 25000000),
        ("Smart Watch X", "Electronics", 4500000),
        ("Running Shoes", "Sports", 1200000),
        ("Cookbook Deluxe", "Books", 350000),
        ("Yoga Mat Premium", "Sports", 750000),
        ("Bluetooth Speaker", "Electronics", 2100000),
        ("Linen Shirt", "Fashion", 480000),
        ("Garden Hose 20m", "Home & Garden", 390000),
        ("Novel Bestseller", "Books", 120000),
        ("4K Monitor", "Electronics", 12500000),
    ]
    regions = ["Hanoi", "Ho Chi Minh", "Da Nang", "Can Tho", "Hai Phong"]
    statuses = ["completed", "processing", "pending", "returned"]
    first_names = ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Vu", "Dang", "Bui", "Do", "Ngo"]
    middle_names = ["Van", "Thi", "Minh", "Quang", "Duc", "Huynh", "Ngoc", "Hai", "Thu", "Xuan"]
    last_names = ["An", "Binh", "Chau", "Dung", "Em", "Giang", "Hung", "Khanh", "Lam", "Mai"]
    
    start_date = datetime.date(2025, 1, 1)
    end_date = datetime.date(2026, 6, 25)
    days_range = (end_date - start_date).days

    buffer = io.StringIO()
    print(f"Generating {num_rows} random rows...")
    
    for i in range(1, num_rows + 1):
        product_name, category, base_val = random.choice(products)
        # Add some variation to value
        value = round(base_val * random.uniform(0.9, 1.1), 2)
        quantity = random.randint(1, 10)
        order_date = start_date + datetime.timedelta(days=random.randint(0, days_range))
        region = random.choice(regions)
        status = random.choice(statuses)
        
        c_name = f"{random.choice(first_names)} {random.choice(middle_names)} {random.choice(last_names)}"
        c_email = f"customer_{i}_{random.randint(1000, 9999)}@example.com"
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Write tab-separated row for COPY command
        buffer.write(f"{product_name}\t{category}\t{value}\t{quantity}\t{order_date}\t{region}\t{status}\t{c_name}\t{c_email}\t{created_at}\n")
        
        if i % 250000 == 0:
            print(f"  Generated {i} rows...")
            
    buffer.seek(0)
    return buffer

def main():
    if not load_env():
        return 1

    # Database parameters
    db_host = os.getenv("SOURCE_DB_HOST", "127.0.0.1")
    db_port = os.getenv("DLH_POSTGRES_PORT", "25432")
    db_name = os.getenv("CUSTOM_DB_NAME", "dlh_custom")
    db_user = os.getenv("CUSTOM_DB_USER", "dlh_custom_user")
    db_password = os.getenv("CUSTOM_DB_PASSWORD", "HoancauIT2026")
    db_schema = os.getenv("CUSTOM_SCHEMA", "custom_schema")
    table_name = "sales_orders"

    print(f"Connecting to database '{db_name}' at {db_host}:{db_port}...")
    try:
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password
        )
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return 1

    t0 = time.time()
    data_buffer = generate_data(1000000)
    t_gen = time.time() - t0
    print(f"✨ Data generated in {t_gen:.2f} seconds.")

    try:
        with conn.cursor() as cur:
            # Re-create table inside custom schema
            print(f"Ensuring table '{db_schema}'.'{table_name}' exists...")
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{db_schema}";')
            cur.execute(f"""
                DROP TABLE IF EXISTS "{db_schema}"."{table_name}";
                CREATE TABLE "{db_schema}"."{table_name}" (
                    id           SERIAL PRIMARY KEY,
                    product_name TEXT NOT NULL,
                    category     TEXT,
                    value        NUMERIC(14,2),
                    quantity     INTEGER,
                    order_date   DATE,
                    region       TEXT,
                    status       TEXT,
                    customer_name TEXT,
                    customer_email TEXT,
                    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            conn.commit()

            print("Loading 1,000,000 rows into PostgreSQL using COPY...")
            t_load = time.time()
            cur.copy_expert(
                sql=f"""
                    COPY "{db_schema}"."{table_name}" 
                    (product_name, category, value, quantity, order_date, region, status, customer_name, customer_email, created_at) 
                    FROM STDIN WITH (FORMAT text, NULL '')
                """,
                file=data_buffer
            )
            conn.commit()
            t_load_elapsed = time.time() - t_load
            print(f"✅ Loaded 1,000,000 rows into PostgreSQL in {t_load_elapsed:.2f} seconds!")
            
            # Check row count
            cur.execute(f'SELECT COUNT(*) FROM "{db_schema}"."{table_name}"')
            print(f"📊 Total rows in '{db_schema}'.'{table_name}': {cur.fetchone()[0]:,}")

    except Exception as e:
        print(f"❌ Database error: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()
    
    print("🚀 Database prep complete!")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
