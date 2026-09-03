# Olist Delivery Performance — Technical and Business Report

> **Status: skeleton.** Fill in from the notebook outputs in Phase 9. The structure
> below follows the course guide's recommended report shape; every section names the
> evidence it must carry, so nothing gets written without a number behind it.

---

## 1. Executive summary

*Three sentences on the problem, three insights, three actions. Written last.*

| | |
|---|---|
| Business question | Where and when are deliveries late, and what does it cost us? |
| Headline late rate | *fill from notebook 02* |
| Revenue delivered late | *fill* |
| Satisfaction penalty | *fill* stars |
| Top recommendation | *fill* |

## 2. Data and method

- Source, licence, coverage window, snapshot date → `docs/data_dictionary.md`
- KPI definitions, exclusions, fixed parameters → `docs/metric_dictionary.md`
- Known limitations, stated up front → `docs/metric_dictionary.md` §5

## 3. Architecture and engineering

- The diagram (`docs/architecture.png`) — layers, direction, quality gates, consumers
- Why these tools and what each one beat → the six [ADRs](adr/)
- Reproducibility: `make all` from a clean clone, idempotency evidence
- Cost control: the partition-pruning benchmark from notebook 02 §6

## 4. Data model

- Star schema diagram (`docs/star_schema.png`)
- Grain declarations and why order grain for delivery → [ADR-004](adr/004-order-grain-and-fanout.md)
- The four fan-out controls, with the numbers from notebook 01 §4

## 5. Data quality

- The test matrix and severity policy → [ADR-006](adr/006-quality-gate-split.md)
- **The fault-injection demonstration**: red build, failing rows, downstream blocked,
  fix, green build. Screenshots in `docs/evidence/`.
- What each gate prevented, in business terms

## 6. Findings

Each finding uses the five-part insight card. An observation without an action is not
a finding.

### 6.1 WHERE deliveries are late
*Observation · Interpretation · Decision · Expected impact · Caveat*

### 6.2 WHEN, and where the time goes
*Observation · Interpretation · Decision · Expected impact · Caveat*

### 6.3 What lateness costs
*Observation · Interpretation · Decision · Expected impact · Caveat*
*Caveat is mandatory here: correlational, controlled for state and category only.*

### 6.4 Supporting KPIs
Monthly sales trend, top products, customer segmentation — each cross-read against
delivery, from notebook 03.

## 7. Conclusion and next steps

| Recommendation | Owner | KPI to watch | Timeframe |
|---|---|---|---|
| | | | |

Proposed experiment to test the causal claim: *A/B or quasi-experimental design.*

## 8. Future architecture

What we would add, and the threshold that would trigger it →
[ADR-005](adr/005-orchestration-scope.md). Streaming, Spark and incremental models are
described as a roadmap with entry conditions, not as things we should have built.
