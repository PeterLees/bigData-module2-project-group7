"""Shared BigQuery connection and chart styling.

Imported by BOTH the analysis notebooks and the Streamlit dashboard, which is
why it sits at the repository root rather than inside either of them. If the
dashboard resolved its own datasets, the dashboard and the notebooks could
quietly end up reading different data while both looked correct.

The brief asks for a SQLAlchemy connection, and there is a practical reason to
route every notebook through one here rather than using the BigQuery client
directly: it keeps the connection string, the dataset resolution and the "which
target am I reading?" logic in a single place, so three notebooks cannot quietly
end up reading three different datasets.

Every notebook reads from the MARTS layer only. No notebook opens a CSV, and no
notebook queries raw. If a number cannot be produced from marts, the fix is a
dbt model, not a pandas workaround in a notebook -- otherwise the definition
lives in a notebook nobody tests.

Usage
-----
    from warehouse import q, marts, SNAPSHOT_DATE

    df = q(f"select * from {marts('agg_delivery_by_route')} where is_reportable")
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

REPO_ROOT = Path(__file__).resolve().parent
load_dotenv(REPO_ROOT / ".env")

PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION = os.getenv("GCP_LOCATION", "US")
DBT_TARGET = os.getenv("DBT_TARGET", "dev")

# The analytical "today". Every recency calculation measures against this, not
# against the real current date: the export ends in late 2018, so using today
# would mark the entire customer base dormant. Must match the
# olist_snapshot_date var in dbt_project.yml.
SNAPSHOT_DATE = os.getenv("OLIST_SNAPSHOT_DATE", "2018-10-17")

if not PROJECT_ID:
    raise RuntimeError(
        "GCP_PROJECT_ID is not set. Copy .env.example to .env and fill it in "
        "(development plan, Section 7 Step E)."
    )


def _dataset(layer: str) -> str:
    """Resolve a logical layer to the dataset dbt actually wrote it to.

    Mirrors macros/generate_schema_name.sql: the prod and ci targets write to
    olist_<layer>, while a developer's dev target writes to
    dbt_<name>_<layer> so nobody can overwrite anyone else's tables.
    """
    if DBT_TARGET in ("prod", "ci"):
        return f"olist_{layer}"
    dev_dataset = os.getenv("DBT_DEV_DATASET")
    if not dev_dataset:
        raise RuntimeError("DBT_TARGET is 'dev' but DBT_DEV_DATASET is not set.")
    return f"{dev_dataset}_{layer}"


def marts(table: str) -> str:
    """Fully-qualified, backtick-quoted marts table reference."""
    return f"`{PROJECT_ID}.{_dataset('marts')}.{table}`"


def staging(table: str) -> str:
    """Fully-qualified staging reference. For reconciliation checks only."""
    return f"`{PROJECT_ID}.{_dataset('staging')}.{table}`"


def raw(table: str) -> str:
    """Fully-qualified raw reference. For the profiling notebook only."""
    dataset = os.getenv("BQ_DATASET_RAW", "olist_raw")
    return f"`{PROJECT_ID}.{dataset}.{table}`"


# Authentication is Application Default Credentials, created by
# `gcloud auth application-default login`. No key file is ever read.
ENGINE = create_engine(f"bigquery://{PROJECT_ID}", location=LOCATION)


def q(sql: str) -> pd.DataFrame:
    """Run a query and return a DataFrame.

    Deliberately thin. Prefer pushing aggregation into BigQuery over pulling
    rows into pandas: it is faster, it scans less, and -- more importantly for
    this project -- a metric computed in SQL against a tested model is
    reproducible, while the same metric recomputed in pandas is not.
    """
    return pd.read_sql(sql, ENGINE)


def bytes_billed(sql: str) -> int:
    """Dry-run a query and return the bytes it would scan.

    Used by the partitioning and clustering benchmark. A dry run costs nothing
    and does not touch the result cache, so the comparison is honest.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT_ID, location=LOCATION)
    job = client.query(
        sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    )
    return job.total_bytes_processed


# --------------------------------------------------------------------------- #
# Chart styling
# --------------------------------------------------------------------------- #
# One palette and one set of defaults across all three notebooks, so the deck
# does not look like it was assembled from three different projects.
PALETTE = {
    "primary": "#1f3864",
    "accent": "#c55a11",
    "good": "#2e7d32",
    "bad": "#c62828",
    "muted": "#8a8a8a",
    "grid": "#dde3ea",
}


def style_charts() -> None:
    """Apply the shared matplotlib defaults. Call once per notebook."""
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "figure.figsize": (11, 5),
            "figure.dpi": 110,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": PALETTE["grid"],
            "grid.linewidth": 0.8,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 10,
            "axes.labelcolor": "#333333",
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.frameon": False,
            "font.size": 10,
        }
    )


def describe_connection() -> str:
    return (
        f"project={PROJECT_ID}  location={LOCATION}  target={DBT_TARGET}\n"
        f"marts dataset={_dataset('marts')}\n"
        f"analytical snapshot date={SNAPSHOT_DATE}"
    )
