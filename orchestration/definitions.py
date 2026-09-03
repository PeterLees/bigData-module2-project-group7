"""Dagster orchestration for the Olist delivery-performance pipeline.

Why an orchestrator at all, when a Makefile already runs the steps: a Makefile
runs commands in order and stops on the first non-zero exit. An orchestrator
models the DATA, records what was materialised and when, retries only the steps
that are safe to retry, and -- the part that matters here -- refuses to build
downstream assets when an upstream quality gate fails. A cron job that runs
everything regardless of failure is scheduling, not orchestration.

The asset graph:

    olist_source_manifest        checksums and row counts of the local CSVs
            |
    raw_file_quality_gate        GREAT EXPECTATIONS -- blocks everything below
            |
    olist_raw_tables             GCS upload + BigQuery load + reconciliation
            |
    dbt assets (via dagster-dbt) stg_* -> int_* -> dim_*/fct_*/agg_*
                                 each dbt test is an asset check

Run locally:
    export DAGSTER_HOME=$PWD/orchestration/.dagster_home
    dagster dev -f orchestration/definitions.py
"""

# NOTE: deliberately no `from __future__ import annotations` here. Dagster
# resolves the `context` parameter's type hint at decoration time, and
# stringified annotations make AssetExecutionContext unresolvable.

import json
import os
import subprocess
import sys
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    Definitions,
    Failure,
    MetadataValue,
    RetryPolicy,
    ScheduleDefinition,
    define_asset_job,
    asset,
)
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = REPO_ROOT / "dbt_project"

# profiles.yml deliberately does NOT live inside dbt_project/ -- it is
# git-ignored precisely so nobody's personal dev dataset name gets committed,
# and it lives at ~/.dbt/profiles.yml instead (see Step E of the Runbook).
# DbtProject.prepare_if_dev() below runs eagerly at import time and builds its
# own internal DbtCliResource to do so; that internal resource does NOT fall
# back to DBT_PROFILES_DIR or ~/.dbt the way the `dbt` CLI does -- if
# profiles_dir is not passed to DbtProject itself, it defaults to project_dir
# and the import fails with a pydantic ValidationError before a single asset
# is even defined ("dbt_project does not contain a profiles.yml file").
# Passing it here, once, is what the later `resources={"dbt": ...}` block
# further down also reads from -- both must agree.
DBT_PROFILES_DIR = os.environ.get("DBT_PROFILES_DIR", str(Path.home() / ".dbt"))

dbt_project = DbtProject(
    project_dir=DBT_PROJECT_DIR,
    profiles_dir=DBT_PROFILES_DIR,
    target=os.environ.get("DBT_TARGET", "dev"),
)
dbt_project.prepare_if_dev()


def _run(context: AssetExecutionContext, args: list[str]) -> subprocess.CompletedProcess:
    """Run a pipeline step and stream its output into the Dagster run log."""
    context.log.info("$ %s", " ".join(args))
    result = subprocess.run(
        args, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    for line in (result.stdout or "").splitlines():
        context.log.info(line)
    for line in (result.stderr or "").splitlines():
        context.log.warning(line)
    return result


# --------------------------------------------------------------------------- #
# 1. Source manifest
# --------------------------------------------------------------------------- #
@asset(
    group_name="ingestion",
    description=(
        "Checksums, byte sizes and true CSV record counts for the nine Olist "
        "source files. This is the reference every later reconciliation "
        "compares against."
    ),
    compute_kind="python",
)
def olist_source_manifest(context: AssetExecutionContext) -> None:
    result = _run(context, [sys.executable, "ingestion/load_olist.py", "--manifest-only"])
    if result.returncode != 0:
        raise Failure("Manifest generation failed. Are the CSVs in data/raw/?")

    manifest = json.loads((REPO_ROOT / "ingestion" / "manifest.json").read_text())
    rows = {f["table"]: f["rows"] for f in manifest["files"]}
    context.add_output_metadata(
        {
            "batch_id": manifest["batch_id"],
            "files": len(manifest["files"]),
            "total_rows": MetadataValue.int(sum(rows.values())),
            "row_counts": MetadataValue.json(rows),
            "snapshot_date": manifest.get("snapshot_date", ""),
        }
    )


# --------------------------------------------------------------------------- #
# 2. Quality Gate 1 -- the one that makes this orchestration rather than cron
# --------------------------------------------------------------------------- #
@asset(
    deps=[olist_source_manifest],
    group_name="quality",
    description=(
        "QUALITY GATE 1. Validates the CSV files with Great Expectations BEFORE "
        "they reach BigQuery: column set, row count against the manifest, "
        "non-null keys, money ranges and categorical domains. Raising here "
        "stops every downstream asset, so a bad export cannot reach the "
        "warehouse at all -- which is something dbt tests structurally cannot "
        "do, because they only run on data that has already been loaded."
    ),
    compute_kind="great_expectations",
)
def raw_file_quality_gate(context: AssetExecutionContext) -> None:
    result = _run(context, [sys.executable, "quality/run_raw_gate.py"])
    if result.returncode != 0:
        raise Failure(
            description=(
                "Raw file validation FAILED. The BigQuery load and every "
                "downstream model have been blocked deliberately. Inspect the "
                "logged expectation failures, fix the source data, and rerun."
            ),
            metadata={"stdout": MetadataValue.md(f"```\n{result.stdout[-4000:]}\n```")},
        )
    context.add_output_metadata({"gate": "PASS", "blocks_downstream_on_failure": True})


# --------------------------------------------------------------------------- #
# 3. Load
# --------------------------------------------------------------------------- #
@asset(
    deps=[raw_file_quality_gate],
    group_name="ingestion",
    description=(
        "Uploads the CSVs to the GCS landing prefix and loads them into the "
        "olist_raw BigQuery dataset with explicit schemas, then reconciles "
        "BigQuery row counts against the manifest. Uses WRITE_TRUNCATE, so it "
        "is idempotent and safe to retry."
    ),
    compute_kind="bigquery",
    # Retried because the load is genuinely idempotent: a transient GCS or
    # BigQuery error should not fail the run. Transformation steps below are
    # NOT retried, because a failing model is a code defect and repeating it
    # just hides the signal.
    retry_policy=RetryPolicy(max_retries=2, delay=30),
)
def olist_raw_tables(context: AssetExecutionContext) -> None:
    result = _run(context, [sys.executable, "ingestion/load_olist.py"])
    if result.returncode != 0:
        raise Failure("BigQuery load or row-count reconciliation failed.")
    context.add_output_metadata(
        {"reconciliation": "PASS", "stdout": MetadataValue.md(f"```\n{result.stdout[-4000:]}\n```")}
    )


# --------------------------------------------------------------------------- #
# 4. dbt -- every model an asset, every dbt test an asset check
# --------------------------------------------------------------------------- #
@dbt_assets(manifest=dbt_project.manifest_path)
def olist_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    """staging -> intermediate -> marts, with every dbt test as an asset check."""
    # `build` rather than `run`: it interleaves tests with models in dependency
    # order, so a failing test stops its own downstream models rather than
    # being discovered after everything has already been published.
    yield from dbt.cli(["build"], context=context).stream()


# --------------------------------------------------------------------------- #
# Jobs and schedules
# --------------------------------------------------------------------------- #
full_pipeline_job = define_asset_job(
    name="olist_full_pipeline",
    description="Manifest -> quality gate -> load -> dbt build. The whole pipeline.",
    selection="*",
)

daily_schedule = ScheduleDefinition(
    name="olist_daily_refresh",
    job=full_pipeline_job,
    # 02:00 local. The source is a static export, so this schedule exists to
    # prove the pipeline reruns cleanly and to catch drift, not because new
    # data arrives overnight. That is stated plainly rather than implied.
    cron_schedule="0 2 * * *",
    execution_timezone="Asia/Singapore",
)

defs = Definitions(
    assets=[
        olist_source_manifest,
        raw_file_quality_gate,
        olist_raw_tables,
        olist_dbt_assets,
    ],
    jobs=[full_pipeline_job],
    schedules=[daily_schedule],
    resources={
        "dbt": DbtCliResource(
            project_dir=dbt_project,
            # Same DBT_PROFILES_DIR resolved once at the top of this file, so
            # the eager prepare_if_dev() call above and this resource can never
            # disagree about where profiles.yml lives.
            profiles_dir=DBT_PROFILES_DIR,
            target=os.environ.get("DBT_TARGET", "dev"),
        )
    },
)
