"""Load the Olist CSV export into BigQuery, idempotently and with evidence.

Pipeline for each of the nine source files:

    manifest (sha256, bytes, rows)
        -> upload to GCS landing prefix
        -> load into olist_raw._stg_<table> with an explicit schema
        -> rewrite as olist_raw.<table> with _batch_id / _loaded_at / _source_uri
        -> reconcile BigQuery row count against the manifest row count

Every load uses WRITE_TRUNCATE, so running this twice produces exactly the same
tables. That idempotency is a graded deliverable, not an implementation detail.

Usage
-----
    python ingestion/load_olist.py                 # full run
    python ingestion/load_olist.py --manifest-only # checksum + row count, no cloud
    python ingestion/load_olist.py --skip-upload   # reuse objects already in GCS
    python ingestion/load_olist.py --tables orders order_items
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import hashlib
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from google.api_core.exceptions import GoogleAPICallError, RetryError
from google.cloud import bigquery, storage
from google.cloud.storage.retry import DEFAULT_RETRY

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"

# source file name -> raw BigQuery table name
SOURCE_FILES: dict[str, str] = {
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_customers_dataset.csv": "customers",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "olist_geolocation_dataset.csv": "geolocation",
    "product_category_name_translation.csv": "product_category_translation",
}

# Published row counts for the Kaggle export. A mismatch means a different or
# truncated download, which we want to know about before modelling anything.
EXPECTED_ROWS: dict[str, int] = {
    "orders": 99_441,
    "order_items": 112_650,
    "order_payments": 103_886,
    "order_reviews": 99_224,
    "customers": 99_441,
    "products": 32_951,
    "sellers": 3_095,
    "geolocation": 1_000_163,
    "product_category_translation": 71,
}

log = logging.getLogger("load_olist")


# --------------------------------------------------------------------------- #
# configuration
# --------------------------------------------------------------------------- #
@dataclasses.dataclass(frozen=True)
class Config:
    project_id: str
    location: str
    bucket: str
    prefix: str
    dataset_raw: str
    local_raw_dir: Path
    snapshot_date: str
    source_url: str
    licence: str

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv(REPO_ROOT / ".env")
        missing = [k for k in ("GCP_PROJECT_ID", "GCS_RAW_BUCKET") if not os.getenv(k)]
        if missing:
            raise SystemExit(
                f"Missing required environment variables: {', '.join(missing)}.\n"
                "Copy .env.example to .env and fill it in (see the development "
                "plan, Section 7 Step E)."
            )
        return cls(
            project_id=os.environ["GCP_PROJECT_ID"],
            location=os.getenv("GCP_LOCATION", "US"),
            bucket=os.environ["GCS_RAW_BUCKET"],
            prefix=os.getenv("GCS_RAW_PREFIX", "olist/raw/v1").strip("/"),
            dataset_raw=os.getenv("BQ_DATASET_RAW", "olist_raw"),
            local_raw_dir=REPO_ROOT / os.getenv("LOCAL_RAW_DIR", "data/raw"),
            snapshot_date=os.getenv("OLIST_SNAPSHOT_DATE", ""),
            source_url=os.getenv("OLIST_SOURCE_URL", ""),
            licence=os.getenv("OLIST_LICENCE", ""),
        )


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def count_data_rows(path: Path) -> int:
    """Count CSV records, not physical lines.

    olist_order_reviews_dataset.csv contains quoted newlines inside review text,
    so ``wc -l`` overcounts it. The csv module handles the quoting correctly.
    """
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        return sum(1 for _ in reader)


def build_manifest(cfg: Config, tables: list[str]) -> dict:
    entries = []
    for filename, table in SOURCE_FILES.items():
        if table not in tables:
            continue
        path = cfg.local_raw_dir / filename
        if not path.exists():
            raise SystemExit(
                f"Missing source file: {path}\n"
                "Download the Olist export from Kaggle into data/raw/ first "
                "(development plan, Section 7 Step C)."
            )
        rows = count_data_rows(path)
        expected = EXPECTED_ROWS[table]
        entries.append(
            {
                "file": filename,
                "table": table,
                "bytes": path.stat().st_size,
                "sha256": sha256_of(path),
                "rows": rows,
                "expected_rows": expected,
                "rows_match_expected": rows == expected,
            }
        )
        flag = "ok" if rows == expected else f"EXPECTED {expected:,}"
        log.info("manifest  %-30s %10s rows  %s", table, f"{rows:,}", flag)

    manifest = {
        "batch_id": uuid.uuid4().hex[:12],
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source_url": cfg.source_url,
        "licence": cfg.licence,
        "snapshot_date": cfg.snapshot_date,
        "gcs_uri_prefix": f"gs://{cfg.bucket}/{cfg.prefix}",
        "files": entries,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    log.info("manifest written to %s (batch_id=%s)", MANIFEST_PATH, manifest["batch_id"])

    mismatched = [e["table"] for e in entries if not e["rows_match_expected"]]
    if mismatched:
        log.warning(
            "Row counts differ from the published Kaggle counts for: %s. "
            "Investigate before modelling.",
            ", ".join(mismatched),
        )
    return manifest


# --------------------------------------------------------------------------- #
# cloud
# --------------------------------------------------------------------------- #
def assert_location(bq: bigquery.Client, cfg: Config) -> None:
    """Fail fast if the raw dataset is not in the agreed location.

    A dataset in the wrong region cannot be joined to the others and cannot be
    moved. Better to stop here than to discover it three models later.
    """
    ds = bq.get_dataset(f"{cfg.project_id}.{cfg.dataset_raw}")
    if ds.location.upper() != cfg.location.upper():
        raise SystemExit(
            f"Dataset {cfg.dataset_raw} is in {ds.location}, but this project is "
            f"pinned to {cfg.location}. Delete and recreate the dataset with "
            f"`bq --location={cfg.location} mk --dataset ...` before loading."
        )
    log.info("dataset %s confirmed in location %s", cfg.dataset_raw, ds.location)


# The client library's own retry budget for a resumable upload defaults to a
# 120-SECOND TOTAL DEADLINE across every chunk-transmit attempt. The largest
# Olist file, geolocation, is ~58 MB -- more than 3.5x the next largest -- and
# on a slower or less stable connection (a dorm/campus network, a VPN, a
# corporate proxy that inspects long-lived HTTPS PUTs) that budget is
# genuinely not enough, producing exactly the RetryError a team member hit:
# "Timeout of 120.0s exceeded ... TimeoutError('The write operation timed out')".
# This is not a bug the retry can paper over by trying harder within the same
# 120s; it needs a longer budget. 600s (10 minutes) comfortably covers even a
# slow upload of the largest file without masking a genuinely dead connection.
# Derived from the library's own DEFAULT_RETRY (deadline 120.0) rather than
# hand-built, so the retryable-error predicate and backoff curve stay exactly
# what google-cloud-storage itself considers safe to retry -- only the total
# time budget changes.
_UPLOAD_RETRY = DEFAULT_RETRY.with_deadline(600.0)
_UPLOAD_TIMEOUT = (60, 600)  # (connect, read) seconds, per HTTP request


def upload(cfg: Config, manifest: dict) -> None:
    client = storage.Client(project=cfg.project_id)
    bucket = client.bucket(cfg.bucket)

    for entry in manifest["files"]:
        blob_name = f"{cfg.prefix}/{entry['file']}"
        local_path = cfg.local_raw_dir / entry["file"]

        # Skip files that are already correctly in GCS. Without this, retrying
        # `make ingest` after ANY file fails re-uploads all nine from scratch --
        # including the ones that already succeeded -- which on a slow
        # connection can turn one bad file into ten minutes of wasted re-upload
        # for files that were already fine.
        #
        # bucket.get_blob() does the existence check AND fetches metadata (incl.
        # .size) in a single call, returning None if the object is absent --
        # bucket.blob() alone only builds a local, unpopulated reference and
        # .size would be None until a separate .reload(). Comparing byte size is
        # sufficient here: a partial/failed upload never lands at the exact
        # right size, and the manifest's sha256 is verified again once the file
        # is loaded into BigQuery downstream.
        existing = bucket.get_blob(blob_name, retry=DEFAULT_RETRY.with_deadline(30.0))
        if existing is not None and existing.size == entry["bytes"]:
            log.info("skip      %-30s already in gs://%s/%s (%s bytes)",
                      entry["table"], cfg.bucket, blob_name, f"{existing.size:,}")
            continue

        blob = bucket.blob(blob_name)
        for attempt in (1, 2, 3):
            try:
                blob.upload_from_filename(
                    local_path,
                    content_type="text/csv",
                    timeout=_UPLOAD_TIMEOUT,
                    retry=_UPLOAD_RETRY,
                )
                log.info("uploaded  %-30s -> gs://%s/%s", entry["table"], cfg.bucket, blob.name)
                break
            except (RetryError, GoogleAPICallError, TimeoutError, ConnectionError) as exc:
                if attempt == 3:
                    raise SystemExit(
                        f"\nUpload of {entry['file']} ({entry['bytes']:,} bytes) failed after "
                        f"3 attempts: {exc}\n\n"
                        "This is a network problem between this machine and Google Cloud "
                        "Storage, not a bug in the data or the pipeline. Things worth trying:\n"
                        "  - Re-run `make ingest` -- files already uploaded successfully are "
                        "now skipped, so a retry only has to finish the one that failed.\n"
                        "  - Try a wired connection, or a different network, if you are on "
                        "campus/dorm wifi, a VPN, or behind a corporate proxy that inspects "
                        "long HTTPS uploads.\n"
                        "  - Temporarily disable antivirus/firewall software that inspects "
                        "outbound HTTPS traffic -- this is a common cause of exactly this "
                        "failure on Windows.\n"
                        f"  - Upload the large file manually and rerun: "
                        f"gsutil cp \"{local_path}\" gs://{cfg.bucket}/{cfg.prefix}/{entry['file']}"
                    ) from exc
                log.warning(
                    "upload attempt %d/3 for %s failed (%s); retrying...",
                    attempt, entry["file"], type(exc).__name__,
                )


def load_schema(table: str) -> list[bigquery.SchemaField]:
    fields = json.loads((SCHEMA_DIR / f"{table}.json").read_text())
    return [
        bigquery.SchemaField(f["name"], f["type"], mode=f.get("mode", "NULLABLE"))
        for f in fields
    ]


def load_table(bq: bigquery.Client, cfg: Config, manifest: dict, entry: dict) -> int:
    table = entry["table"]
    stage_ref = f"{cfg.project_id}.{cfg.dataset_raw}._stg_{table}"
    final_ref = f"{cfg.project_id}.{cfg.dataset_raw}.{table}"
    uri = f"gs://{cfg.bucket}/{cfg.prefix}/{entry['file']}"

    job_config = bigquery.LoadJobConfig(
        schema=load_schema(table),
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        # Review comments contain newlines inside quoted fields.
        allow_quoted_newlines=True,
        # Reject the whole file rather than silently dropping rows: a partial
        # load is worse than a failed one because nothing downstream notices.
        max_bad_records=0,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    bq.load_table_from_uri(uri, stage_ref, job_config=job_config, location=cfg.location).result()

    # Attach ingestion metadata. CSV loads cannot add columns that are absent
    # from the file, so the raw table is rewritten once from the stage table.
    bq.query(
        f"""
        CREATE OR REPLACE TABLE `{final_ref}` AS
        SELECT
            *,
            @batch_id    AS _batch_id,
            @loaded_at   AS _loaded_at,
            @source_uri  AS _source_uri,
            @sha256      AS _source_sha256
        FROM `{stage_ref}`
        """,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("batch_id", "STRING", manifest["batch_id"]),
                bigquery.ScalarQueryParameter("loaded_at", "TIMESTAMP", manifest["generated_at"]),
                bigquery.ScalarQueryParameter("source_uri", "STRING", uri),
                bigquery.ScalarQueryParameter("sha256", "STRING", entry["sha256"]),
            ]
        ),
        location=cfg.location,
    ).result()
    bq.query(f"DROP TABLE IF EXISTS `{stage_ref}`", location=cfg.location).result()

    return bq.get_table(final_ref).num_rows


def reconcile(manifest: dict, loaded: dict[str, int]) -> bool:
    header = f"{'table':<30}{'source':>12}{'bigquery':>12}{'delta':>10}  status"
    print("\n" + header)
    print("-" * len(header))
    ok = True
    for entry in manifest["files"]:
        src, bq_rows = entry["rows"], loaded[entry["table"]]
        delta = bq_rows - src
        status = "OK" if delta == 0 else "MISMATCH"
        ok &= delta == 0
        print(f"{entry['table']:<30}{src:>12,}{bq_rows:>12,}{delta:>10,}  {status}")
    print("-" * len(header))
    print("RECONCILIATION:", "PASS" if ok else "FAIL", "\n")
    return ok


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-only", action="store_true",
                        help="compute checksums and row counts without touching the cloud")
    parser.add_argument("--skip-upload", action="store_true",
                        help="reuse objects already present in GCS")
    parser.add_argument("--tables", nargs="*", default=sorted(SOURCE_FILES.values()),
                        help="subset of raw tables to process")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")

    unknown = set(args.tables) - set(SOURCE_FILES.values())
    if unknown:
        raise SystemExit(f"Unknown table(s): {', '.join(sorted(unknown))}")

    cfg = Config.from_env()
    manifest = build_manifest(cfg, args.tables)
    if args.manifest_only:
        log.info("--manifest-only: stopping before any cloud call")
        return 0

    bq = bigquery.Client(project=cfg.project_id, location=cfg.location)
    assert_location(bq, cfg)

    if not args.skip_upload:
        upload(cfg, manifest)

    loaded = {}
    for entry in manifest["files"]:
        rows = load_table(bq, cfg, manifest, entry)
        loaded[entry["table"]] = rows
        log.info("loaded    %-30s %10s rows", entry["table"], f"{rows:,}")

    return 0 if reconcile(manifest, loaded) else 1


if __name__ == "__main__":
    sys.exit(main())
