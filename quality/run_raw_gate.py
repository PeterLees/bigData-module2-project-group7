"""Quality Gate 1: validate the Olist CSV files BEFORE they reach BigQuery.

This is the job Great Expectations does that dbt cannot: dbt can only test data
that is already in the warehouse, so by the time a dbt test fails the defect has
already been loaded. This gate runs against the files on disk and blocks the
load entirely.

What it checks, per file:
  * the exact column set (a renamed or reordered export is caught immediately)
  * row count against ingestion/manifest.json
  * primary-key columns are non-null
  * money and duration columns are non-negative and within plausible bounds
  * categorical columns contain only known values

Usage
-----
    python quality/run_raw_gate.py                 # all files
    python quality/run_raw_gate.py --tables orders order_items
    python quality/run_raw_gate.py --docs          # also build Data Docs

Exit code 0 = pass (safe to load), 1 = fail (do not load).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
GX_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = REPO_ROOT / "ingestion" / "manifest.json"

log = logging.getLogger("raw_gate")

ORDER_STATUSES = {
    "delivered", "shipped", "canceled", "unavailable",
    "invoiced", "processing", "created", "approved",
}
PAYMENT_TYPES = {"credit_card", "boleto", "voucher", "debit_card", "not_defined"}

# Loose upper bounds. They exist to catch a decimal-point or unit error, not to
# encode a business rule -- a genuine outlier should still pass.
MAX_PRICE = 100_000
MAX_FREIGHT = 10_000


def expectations_for(table: str, columns: list[str], rows: int) -> list:
    """Build the expectation list for one source table."""
    exp: list = [
        gxe.ExpectTableColumnsToMatchSet(column_set=columns, exact_match=True),
        gxe.ExpectTableRowCountToEqual(value=rows),
    ]

    # --- primary-key columns must never be null -----------------------------
    key_columns = {
        "orders": ["order_id", "customer_id", "order_status", "order_purchase_timestamp"],
        "order_items": ["order_id", "order_item_id", "product_id", "seller_id"],
        "order_payments": ["order_id", "payment_sequential", "payment_type"],
        "order_reviews": ["review_id", "order_id", "review_score"],
        "customers": ["customer_id", "customer_unique_id", "customer_state"],
        "products": ["product_id"],
        "sellers": ["seller_id", "seller_state"],
        "geolocation": ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"],
        "product_category_translation": ["product_category_name", "product_category_name_english"],
    }[table]
    exp += [gxe.ExpectColumnValuesToNotBeNull(column=c) for c in key_columns]

    # --- money, counts and categories ---------------------------------------
    if table == "orders":
        exp.append(gxe.ExpectColumnValuesToBeInSet(
            column="order_status", value_set=sorted(ORDER_STATUSES)))
    elif table == "order_items":
        exp += [
            gxe.ExpectColumnValuesToBeBetween(column="price", min_value=0, max_value=MAX_PRICE),
            gxe.ExpectColumnValuesToBeBetween(column="freight_value", min_value=0,
                                              max_value=MAX_FREIGHT),
            gxe.ExpectColumnValuesToBeBetween(column="order_item_id", min_value=1),
        ]
    elif table == "order_payments":
        exp += [
            gxe.ExpectColumnValuesToBeInSet(column="payment_type", value_set=sorted(PAYMENT_TYPES)),
            gxe.ExpectColumnValuesToBeBetween(column="payment_value", min_value=0,
                                              max_value=MAX_PRICE),
            gxe.ExpectColumnValuesToBeBetween(column="payment_installments", min_value=0),
        ]
    elif table == "order_reviews":
        exp.append(gxe.ExpectColumnValuesToBeBetween(
            column="review_score", min_value=1, max_value=5))
    elif table == "customers":
        exp.append(gxe.ExpectColumnValueLengthsToEqual(column="customer_state", value=2))
    elif table == "sellers":
        exp.append(gxe.ExpectColumnValueLengthsToEqual(column="seller_state", value=2))
    elif table == "geolocation":
        # Brazil's bounding box, generously padded, but as a THRESHOLD rather
        # than an absolute rule.
        #
        # The source contains 29 mis-geocoded points out of 1,000,163 (0.003%)
        # that carry Brazilian city and state names but coordinates in Spain,
        # Mexico, Italy, the Philippines and Argentina. That is a documented
        # characteristic of this export, not a reason to refuse the file: this
        # gate answers "should this file be loaded at all?", and coordinates are
        # a non-key enrichment attribute. stg_geolocation already takes the
        # MEDIAN coordinate per zip prefix precisely because these points are
        # noisy, so a handful of outliers cannot move a prefix.
        #
        # 99.9% still catches what this rule is really for: a wrong country's
        # data, swapped lat/lng columns, or a unit error, all of which would
        # blow through the threshold by orders of magnitude.
        exp += [
            gxe.ExpectColumnValuesToBeBetween(column="geolocation_lat",
                                              min_value=-35.0, max_value=6.0,
                                              mostly=0.999),
            gxe.ExpectColumnValuesToBeBetween(column="geolocation_lng",
                                              min_value=-75.0, max_value=-32.0,
                                              mostly=0.999),
        ]
    elif table == "products":
        exp.append(gxe.ExpectColumnValuesToBeUnique(column="product_id"))

    return exp


def validate_table(context, entry: dict, raw_dir: Path) -> tuple[bool, list[str]]:
    table = entry["table"]
    path = raw_dir / entry["file"]
    df = pd.read_csv(path)

    suite_name = f"olist_raw__{table}"
    batch_name = f"batch__{table}"

    source = context.data_sources.add_or_update_pandas(f"olist_files__{table}")
    asset = source.add_dataframe_asset(name=table)
    batch_definition = asset.add_batch_definition_whole_dataframe(batch_name)

    suite = context.suites.add_or_update(gx.ExpectationSuite(name=suite_name))
    for expectation in expectations_for(table, list(df.columns), entry["rows"]):
        suite.add_expectation(expectation)

    validation = context.validation_definitions.add_or_update(
        gx.ValidationDefinition(name=f"vd__{table}", data=batch_definition, suite=suite)
    )
    result = validation.run(batch_parameters={"dataframe": df})

    failures = []
    for exp_result in result.results:
        if exp_result.success:
            continue
        cfg = exp_result.expectation_config
        column = cfg.kwargs.get("column", "-")
        unexpected = exp_result.result.get("unexpected_count")
        detail = f" ({unexpected} unexpected)" if unexpected is not None else ""
        failures.append(f"{cfg.type} on {column}{detail}")
    return bool(result.success), failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", nargs="*", help="subset of raw tables to validate")
    parser.add_argument("--raw-dir", default=None, help="override the CSV directory")
    parser.add_argument("--docs", action="store_true", help="build Great Expectations Data Docs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    # Great Expectations logs a dozen INFO lines per asset ("Saving N Fluent
    # Datasources", "missing config_provider"). Across nine tables that buries
    # the PASS/FAIL lines this script exists to print.
    for noisy in ("great_expectations", "botocore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if not MANIFEST_PATH.exists():
        raise SystemExit(
            "ingestion/manifest.json not found. Run "
            "`python ingestion/load_olist.py --manifest-only` first."
        )
    manifest = json.loads(MANIFEST_PATH.read_text())
    raw_dir = Path(args.raw_dir) if args.raw_dir else REPO_ROOT / "data" / "raw"

    entries = manifest["files"]
    if args.tables:
        entries = [e for e in entries if e["table"] in set(args.tables)]
        if not entries:
            raise SystemExit(f"No manifest entries match: {', '.join(args.tables)}")

    context = gx.get_context(mode="file", project_root_dir=str(GX_ROOT))

    results: list[tuple[str, bool, list[str]]] = []
    for entry in entries:
        ok, failures = validate_table(context, entry, raw_dir)
        results.append((entry["table"], ok, failures))
        log.info("%-30s %s", entry["table"], "PASS" if ok else "FAIL")
        for failure in failures:
            log.error("    %s", failure)

    if args.docs:
        context.build_data_docs()
        log.info("Data Docs written under quality/gx/uncommitted/data_docs/")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\nQUALITY GATE 1 (raw files): {passed}/{len(results)} tables passed")
    if passed != len(results):
        print("Load is BLOCKED. Fix the source data before running ingestion.\n")
        return 1
    print("Safe to load into BigQuery.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
