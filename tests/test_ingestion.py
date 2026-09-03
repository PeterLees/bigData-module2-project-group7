"""Unit tests for the ingestion helpers.

These run in CI with no cloud credentials, which is the point: the parts of the
loader that are easiest to get quietly wrong -- counting CSV records that
contain embedded newlines, and hashing files reproducibly -- are exactly the
parts that need no BigQuery connection to test.

The embedded-newline case is not hypothetical. olist_order_reviews_dataset.csv
contains review text with line breaks inside quoted fields, so `wc -l` reports
substantially more rows than the file actually has. If the manifest used a naive
line count, the reconciliation against BigQuery would fail on every single run
and the team would learn to ignore it.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))

from load_olist import (  # noqa: E402
    EXPECTED_ROWS,
    SOURCE_FILES,
    count_data_rows,
    sha256_of,
)

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "ingestion" / "schemas"


# --------------------------------------------------------------------------- #
# row counting
# --------------------------------------------------------------------------- #
def test_count_data_rows_excludes_the_header(tmp_path: Path):
    path = tmp_path / "simple.csv"
    path.write_text("a,b\n1,2\n3,4\n")
    assert count_data_rows(path) == 2


def test_count_data_rows_handles_newlines_inside_quoted_fields(tmp_path: Path):
    """The olist_order_reviews case: a naive line count would say 5, not 2."""
    path = tmp_path / "reviews.csv"
    path.write_text(
        'review_id,message\n'
        '1,"first line\nsecond line\nthird line"\n'
        '2,"single line"\n'
    )
    assert path.read_text().count("\n") == 5  # physical lines
    assert count_data_rows(path) == 2  # actual records


def test_count_data_rows_handles_quoted_commas(tmp_path: Path):
    path = tmp_path / "commas.csv"
    path.write_text('id,text\n1,"a, b, c"\n2,"d, e"\n')
    assert count_data_rows(path) == 2


def test_count_data_rows_on_a_header_only_file(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text("a,b,c\n")
    assert count_data_rows(path) == 0


# --------------------------------------------------------------------------- #
# checksums
# --------------------------------------------------------------------------- #
def test_sha256_is_stable_and_content_sensitive(tmp_path: Path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.write_text("identical content")
    b.write_text("identical content")
    c.write_text("different content")

    assert sha256_of(a) == sha256_of(a), "must be deterministic across calls"
    assert sha256_of(a) == sha256_of(b), "same bytes must produce the same digest"
    assert sha256_of(a) != sha256_of(c), "different bytes must produce a different digest"
    assert len(sha256_of(a)) == 64


def test_sha256_reads_the_whole_file_not_just_the_first_chunk(tmp_path: Path):
    """Guards the chunked read loop: a difference past the first block must show."""
    base = "x" * (2 << 20)  # larger than the 1 MiB chunk size
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text(base + "END-A")
    b.write_text(base + "END-B")
    assert sha256_of(a) != sha256_of(b)


# --------------------------------------------------------------------------- #
# configuration consistency
# --------------------------------------------------------------------------- #
def test_every_source_file_has_an_expected_row_count():
    assert set(SOURCE_FILES.values()) == set(EXPECTED_ROWS)


def test_every_source_file_has_an_explicit_schema():
    """No table may fall back to BigQuery autodetect."""
    for table in SOURCE_FILES.values():
        assert (SCHEMA_DIR / f"{table}.json").exists(), f"missing schema for {table}"


@pytest.mark.parametrize("table", sorted(SOURCE_FILES.values()))
def test_schema_files_are_well_formed(table: str):
    fields = json.loads((SCHEMA_DIR / f"{table}.json").read_text())
    assert fields, f"{table} schema is empty"

    allowed_types = {"STRING", "INT64", "NUMERIC", "FLOAT64", "TIMESTAMP", "DATE", "BOOL"}
    names = []
    for field in fields:
        assert set(field) >= {"name", "type"}, f"{table}: malformed field {field}"
        assert field["type"] in allowed_types, f"{table}.{field['name']}: {field['type']}"
        # Raw must accept the file as it is, so defects stay reproducible.
        # Nullability is enforced downstream by dbt, not by rejecting the load.
        assert field.get("mode", "NULLABLE") == "NULLABLE", (
            f"{table}.{field['name']} is not NULLABLE; the raw layer must not "
            "reject rows"
        )
        names.append(field["name"])

    assert len(names) == len(set(names)), f"{table} has duplicate column names"


def test_money_columns_are_numeric_not_float():
    """Float money breaks the exact source-to-mart revenue reconciliation."""
    money = {
        "order_items": ["price", "freight_value"],
        "order_payments": ["payment_value"],
    }
    for table, columns in money.items():
        fields = {f["name"]: f["type"] for f in json.loads((SCHEMA_DIR / f"{table}.json").read_text())}
        for column in columns:
            assert fields[column] == "NUMERIC", (
                f"{table}.{column} must be NUMERIC so money arithmetic is exact"
            )


def test_expected_row_counts_match_the_published_kaggle_export():
    """A tripwire: if someone edits these, the change should be deliberate."""
    assert EXPECTED_ROWS["orders"] == 99_441
    assert EXPECTED_ROWS["order_items"] == 112_650
    assert EXPECTED_ROWS["geolocation"] == 1_000_163
    assert sum(EXPECTED_ROWS.values()) == 1_550_922
