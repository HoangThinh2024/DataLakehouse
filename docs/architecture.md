# Kien Truc Data Lakehouse

Tai lieu nay mo ta kien truc Lakehouse trong du an voi 2 thanh phan chinh:

1. PostgreSQL: luu metadata, danh muc dataset, va lich su chay pipeline.
2. RustFS (S3 API): luu du lieu theo cac tang Bronze, Silver, Gold.

## Quick Start 5 Phut

Thuc hien theo thu tu duoi day de khoi dong va kiem tra he thong:

1. Tao file `.env` (neu chua co) theo mau trong [README.md](../README.md).
2. Khoi dong stack:

```bash
docker compose up -d
```

3. Kiem tra cac service:

```bash
docker compose ps
```

4. Kiem tra bucket Bronze/Silver/Gold da duoc tao:

```bash
docker compose logs rustfs-init
```

5. Kiem tra schema metadata trong PostgreSQL:

```bash
docker exec -it postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dn"
docker exec -it postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt lakehouse.*"
```

Neu muon khoi tao lai tu dau (bao gom script init SQL):

```bash
docker compose down -v
docker compose up -d
```

Luu y: neu ban doi `POSTGRES_PASSWORD` sau khi PostgreSQL volume da duoc khoi tao, can reset volume bang lenh tren. Neu khong, `postgres-bootstrap` se bao loi xac thuc vi volume cu van giu mat khau cu.

## Cac Tang Du Lieu

- Bronze: du lieu raw, giu nguyen trang thai goc.
- Silver: du lieu da duoc lam sach, chuan hoa, bo sung quy tac chat luong.
- Gold: du lieu tong hop, toi uu cho dashboard, bao cao, va API.

## Metadata Model Trong PostgreSQL

Schema `lakehouse` gom cac bang chinh:

- `lakehouse.dataset`: danh muc dataset.
- `lakehouse.data_object`: metadata tung object (bucket, key, format, kich thuoc, partition).
- `lakehouse.pipeline_run`: theo doi moi lan chay pipeline (trang thai, thoi gian, thong ke).

Script khoi tao metadata: [postgres/init/001_lakehouse_metadata.sql](../postgres/init/001_lakehouse_metadata.sql).

## Quy Uoc Luu Tru Tren RustFS

De thong nhat quan ly du lieu, nen dat key theo mau:

- `bronze/<domain>/<dataset>/dt=YYYY-MM-DD/file.parquet`
- `silver/<domain>/<dataset>/dt=YYYY-MM-DD/file.parquet`
- `gold/<domain>/<data_mart>/dt=YYYY-MM-DD/file.parquet`

Quy uoc nay giup:

- De partition pruning khi query.
- De tracing lineage tu object ve dataset.
- De lifecycle management theo tung tang du lieu.

## Luong Du Lieu De Xuat

1. Ingest du lieu raw vao Bronze.
2. Validate schema, quality va transform sang Silver.
3. Tong hop nghiep vu sang Gold.
4. Moi object moi duoc ghi vao RustFS can co metadata tuong ung trong `lakehouse.data_object`.
5. Moi lan chay ETL/ELT can ghi log vao `lakehouse.pipeline_run`.

## Goi Y Mo Rong

1. Orchestration: Airflow hoac Prefect.
2. Query engine: Trino hoac Spark SQL.
3. Data quality: Great Expectations hoac custom checks.
4. Governance: bo sung data catalog va phan quyen theo domain.
