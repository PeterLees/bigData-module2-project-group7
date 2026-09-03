# Olist Delivery Performance — Big Data Module 2, Group 7

An end-to-end analytics pipeline on the Olist Brazilian e-commerce dataset, built to
answer one question well:

> **Where and when are deliveries late, and what does it cost us?**

Raw CSV → GCS landing zone → Great Expectations file gate → BigQuery raw → dbt
(staging → intermediate → marts) → dbt test gate → Jupyter analysis **and a Streamlit
dashboard**, orchestrated by Dagster with GitHub Actions CI.

**24 dbt models · 162 data tests · 2 quality gates · 3 notebooks · 1 dashboard**

---

## Why this project is shaped the way it is

The temptation in a big-data assignment is to add tools. This project deliberately does
the opposite: it picks one defensible business case and lets it determine the grain,
the dimensions, the tests and the final chart. Spark, Kafka and Redis are **excluded on
purpose**, with the threshold that would justify each one written down in
[ADR-005](docs/adr/005-orchestration-scope.md).

Four decisions do most of the work:

1. **Grain before SQL.** Lateness is a property of a shipment, so `fct_orders` is the
   primary fact at order grain. Revenue needs item detail, so `fct_order_items` sits
   beside it. The two never mix. → [ADR-004](docs/adr/004-order-grain-and-fanout.md)
2. **Four fan-out controls**, each in a named model with a uniqueness test, because
   Olist has four documented ways of silently producing a wrong number.
3. **Two quality gates with a real division of labour.** Great Expectations validates
   the *files* before the load — something dbt structurally cannot do. dbt tests own
   everything already in a table. → [ADR-006](docs/adr/006-quality-gate-split.md)
4. **Exact reconciliation.** Total revenue in the marts must equal total revenue in
   staging, to the cent, on every build. If any join anywhere fans out, the build fails
   and nothing publishes.

Full reasoning: **[docs/Module2_Group7_Development_Plan.pdf](docs/Module2_Group7_Development_Plan.pdf)**
· operating instructions: **[docs/Module2_Group7_Runbook.pdf](docs/Module2_Group7_Runbook.pdf)**
· what actually happened on the first real run: **[docs/Module2_Group7_First_Run_Report.pdf](docs/Module2_Group7_First_Run_Report.pdf)**
and the six [ADRs](docs/adr/).

---

## Architecture

```
Kaggle CSV x 9  (static export, ~120 MB, 1.55M rows)
        |
   ingestion/load_olist.py  -->  manifest.json (sha256, bytes, true CSV row counts)
        |
        +--> GCS  gs://<PROJECT_ID>-olist-raw/olist/raw/v1/     immutable, replayable
        |
        +--> QUALITY GATE 1  quality/run_raw_gate.py  (Great Expectations)
        |    columns · row counts · non-null keys · money ranges · domains
        |    FAILS  ->  nothing is loaded
        v
BigQuery  olist_raw.*        explicit schemas, no autodetect
        |                    + _batch_id, _loaded_at, _source_uri, _source_sha256
        v  dbt
olist_staging.stg_*          rename · cast · dedupe · translate · geo-collapse
        v  dbt
olist_staging.int_*          FAN-OUT CONTROLS: payments and reviews to order grain,
        |                    item rollup, delivery milestone maths
        v  dbt
olist_marts.dim_* fct_* agg_*
        |    QUALITY GATE 2  dbt build: 162 tests
        |    keys · relationships · domains · ranges · milestone chronology
        |    · revenue reconciliation      FAILS  ->  marts do not publish
        v
notebooks/ (SQLAlchemy -> pandas)  ·  dashboard/ (Streamlit)  ·  docs/report

Orchestrated by: Dagster asset DAG + daily schedule
Continuously checked by: GitHub Actions on every pull request
```

### Layers

| Dataset | Contents | Who writes it |
|---|---|---|
| `olist_raw` | Source fields exactly as exported, plus ingestion metadata | Platform Owner only |
| `olist_staging` | `stg_*` and `int_*` — cleaning and fan-out controls | dbt |
| `olist_marts` | `dim_*`, `fct_*`, `agg_*` — the consumption contract | dbt, after tests pass |
| `olist_snapshots` | dbt snapshot history | dbt |
| `dbt_<name>_*` | Per-developer sandbox | each developer |

Separating raw from marts means a defect stays reproducible in raw without
contaminating what analysts read, and lets the Analytics Owner have read-only access to
marts alone.

---

## Quick start

Full step-by-step instructions, including the Google Cloud console clicks, are in
Section 7 of the [development plan](docs/Module2_Group7_Development_Plan.pdf), or work through
[notebooks/00_runbook.ipynb](notebooks/00_runbook.ipynb) - the plan and the runbook in one
executable document, where every setup step and every claim the plan makes about the
implementation is checked by a cell rather than asserted.

**Prerequisites:** a GCP project with billing and the BigQuery + Cloud Storage APIs
enabled, and the Olist CSVs downloaded to `data/raw/`.

```bash
# 1. Environment  (Python 3.11 — dbt does not support 3.14)
conda create -y -n bd-m2-g7 python=3.11 && conda activate bd-m2-g7
pip install -r requirements.txt

# 2. Credentials — user OAuth, never a downloaded service-account key
gcloud auth login
gcloud auth application-default login
gcloud config set project <PROJECT_ID>

# 3. Configure
cp .env.example .env          # fill in PROJECT_ID, bucket, your dev dataset
cp dbt_project/profiles.yml.example ~/.dbt/profiles.yml

# 4. Run the whole pipeline
make setup
make all
```

`make all` runs: manifest → GX file gate → BigQuery load → `dbt build` (models,
snapshots and tests in dependency order) → unit tests. Every stage is safe to rerun.

`.env` is loaded and exported by the Makefile, because dbt resolves `env_var()` against
the real process environment and would not otherwise see it.

```bash
make help          # list every target
```

| Target | Does |
|---|---|
| `make manifest` | Checksum and row-count the local CSVs. No cloud calls |
| `make gate` | **Quality Gate 1** — validate the files before loading |
| `make ingest` | Upload to GCS, load into BigQuery, reconcile row counts |
| `make build` | **Quality Gate 2** — `dbt build`: models, snapshots and tests, dependency ordered |
| `make analyse` | Execute the three notebooks top to bottom |
| `make dashboard` | Serve the interactive Streamlit dashboard |
| `make lint` | sqlfluff over all dbt SQL |
| `make unit` | pytest — no credentials needed |
| `make docs` | Generate and serve the dbt lineage graph |
| `make evidence` | Collect test artifacts into `docs/evidence/` for the report |

The dashboard:

```bash
make dashboard
```

Opens at <http://localhost:8501>. Five tabs — **Where**, **When**, **What it costs**,
**Business KPIs** and **Data quality** — with a purchase-month range, destination-region
and minimum-volume filter in the sidebar.

Two rules it follows, both inherited from the architecture rather than from Streamlit
convention:

- **It reads the marts layer only.** No CSV, no raw tables, no local files. Every
  number comes from a dbt model that has tests attached, so the dashboard, the
  notebooks and the report cannot disagree.
- **It does not redefine metrics.** Definitions live in `docs/metric_dictionary.md`.
  Where interactive filtering forces the late rate to be recomputed against
  `fct_orders`, the **Data quality** tab asserts live that the recomputation still
  matches `agg_delivery_monthly` — so the app cannot silently drift from the pipeline.

That last tab is worth showing in the demo: it runs the revenue reconciliation, the
grain check and the person-grain RFM check against the live warehouse, in front of the
audience.

Orchestrated instead of by hand:

```bash
mkdir -p orchestration/.dagster_home
export DAGSTER_HOME=$PWD/orchestration/.dagster_home
dagster dev -f orchestration/definitions.py
```

---

## Repository layout

```
ingestion/       load_olist.py, explicit BigQuery schemas, manifest
quality/         Great Expectations context, suites and the pre-load gate
dbt_project/     24 models, 162 tests, 4 macros, 1 snapshot
notebooks/       00 plan+runbook (executable) | 01 profiling | 02 delivery | 03 KPIs
dashboard/       Streamlit app — the same marts, for people who won't open a notebook
warehouse.py     shared BigQuery connection, imported by BOTH notebooks and dashboard
orchestration/   Dagster assets, job and daily schedule
tests/           pytest for the ingestion helpers
docs/            development plan, ADRs, data + metric dictionaries, evidence
.github/         ci.yml (credential-free) and scheduled.yml (nightly build)
```

---

## Tool choices, in one line each

Full reasoning and rejected alternatives in the [ADRs](docs/adr/).

| Choice | Why, and what it beat |
|---|---|
| **Olist** | Only one of the three permitted datasets with delivery milestones, review scores, money and geography on both sides of a shipment. Instacart has no money columns; London Bicycles has no customer entity, so the required segmentation is impossible. |
| **BigQuery, US multi-region** | The taught stack; free tier covers 120 MB many times over; location pinned before any dataset was created because it is immutable. |
| **ELT with dbt** | Raw stays replayable, transformations are reviewable SQL in Git, and lineage + tests + docs generate from the same models. |
| **Python loader, not Meltano** | Static CSV has no incremental state to manage. Meltano would be configuration around a problem we do not have — documented as the migration path if a live source appears. |
| **GX before load, dbt tests after** | A real division of labour: only GX can reject a malformed file *before* it reaches the warehouse. |
| **Dagster + GitHub Actions** | Asset lineage, retries only where idempotent, and a demonstrable fail-stop. A cron job that runs everything regardless of failure is not orchestration. |
| **No Spark / Kafka / Redis** | 120 MB of static data. Each is excluded with the threshold that would justify it written down. |

---

## Data quality

Two gates, 161 dbt tests plus the GX file suite. Severity is assigned deliberately:
**error** blocks publication, **warn** publishes with an explanation. Nothing fails
silently and nothing is silently coerced.

The tests that matter most are the reconciliations, because they catch the failure that
would otherwise be invisible:

| Test | Asserts |
|---|---|
| `assert_revenue_reconciles_staging_to_mart` | Mart revenue equals staging revenue **exactly**, at NUMERIC precision |
| `assert_order_count_reconciles` | `fct_orders` has exactly one row per staging order |
| `assert_no_payment_fanout` | Per-order payment totals match staging |
| `assert_is_late_matches_delay` | The late flag and the measure behind it can never disagree |
| `assert_delivered_orders_have_delivery_date` | No delivered order silently drops out of the late-rate denominator |
| `assert_delivery_milestones_in_order` | Nothing is delivered before it was shipped |
| `assert_rfm_uses_person_grain` | Segmentation is keyed on the person, not the per-order ID |

A passing suite proves little on its own. **A suite seen to fail correctly proves a
lot** — the fault-injection demonstration (inject a duplicate key and a negative price,
capture the red build, fix, capture green) is a required deliverable, not an extra.

---

## Security

- Local access is **user OAuth**, so every BigQuery job is attributable to a person.
  No service-account key is ever downloaded to a laptop.
- Exactly one service account exists, for CI, with `bigquery.jobUser` plus Data Editor
  on staging and marts only. It **cannot touch `olist_raw`**, so a CI bug can never
  destroy the reproducible copy of the source data.
- `.env`, credential JSON files and everything under `data/` are git-ignored, and CI
  fails the build if any of them become tracked.
- If a key is ever exposed: **revoke it in the console**. Deleting the file in a later
  commit does not remove it from Git history.

---

## Team

| Role | Owns |
|---|---|
| Platform / Ingestion | GCP project, GCS bucket, `olist_raw`, the loader, reconciliation |
| Modeling | dbt models, star schema, ERD |
| Quality | dbt tests, GX suites, the fault-injection demonstration |
| Orchestration / DevOps | Dagster, GitHub Actions, secrets, Makefile |
| Analytics / Communications | Notebooks, metric dictionary, report, executive deck |

One person owns raw uploads. Everyone else develops in their own `dbt_<name>` dataset
and promotes to the shared marts only through a passing build.

---

## Data source

Brazilian E-Commerce Public Dataset by Olist —
<https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>
CC BY-NC-SA 4.0, non-commercial. Coursework use only. Coverage September 2016 –
October 2018. Raw CSVs are **not** committed to this repository.
