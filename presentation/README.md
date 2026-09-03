# Executive deck

10 minutes presenting + 5 minutes Q&A. Mixed technical and business audience. All
members present.

| Time | Content | The one message |
|---|---|---|
| 0:00–1:00 | Problem and executive summary | Late deliveries are concentrated in specific routes and months, they measurably depress review scores, and we can now see exactly where |
| 1:00–2:20 | Data and architecture | The pipeline is rerunnable, clearly layered, and a quality gate stops bad data before anyone sees it |
| 2:20–3:30 | Model and definitions | Declared grain and reconciliation testing stop revenue being inflated by joins and the late rate being diluted by undelivered orders |
| 3:30–7:30 | The delivery findings: where, when, what it costs | Each one: evidence, then meaning, then the action. Nothing else |
| 7:30–8:40 | Quality and risk | Here is a test failing on purpose, here is what it caught, here is what our data cannot tell you |
| 8:40–10:00 | Recommendations and roadmap | These are the owners, the KPIs, and the next experiment |

Q&A preparation is in Section 13.1 of the development plan. Every member should be able
to answer at least: why Olist, why order grain, how do you know revenue is right, why
not Spark, and what happens when a test fails.

Charts come from the notebooks — do not rebuild them in the slide tool, or the deck and
the pipeline will drift apart.
