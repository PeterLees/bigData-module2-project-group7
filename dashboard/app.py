"""Olist Delivery Performance — interactive dashboard.

Answers the project's business case (Business Case 3: where and when are
deliveries late, and what does it cost us?) for someone who will not open a
notebook.

Two rules this app follows, both of which come from the project's architecture
rather than from Streamlit convention:

1. IT READS THE MARTS LAYER ONLY. No CSV, no raw tables, no local files. Every
   number shown here comes from a dbt model that has tests attached to it. If a
   figure is wrong, it is wrong in a tested model and it is wrong identically in
   the notebooks and the report -- rather than being a fourth, untested version
   of the truth.

2. IT DOES NOT REDEFINE METRICS. The definitions live in
   docs/metric_dictionary.md and are implemented in dbt. Where interactive
   filtering forces a metric to be recomputed against fct_orders (because a
   pre-aggregated model cannot be sliced by an arbitrary filter combination),
   the SQL is confined to LATE_RATE_SQL below and the Data Quality tab checks it
   still agrees with agg_delivery_monthly.

Run:
    make dashboard
    # or: streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Olist Delivery Performance",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# warehouse.py sits at the repository root precisely so this app and the
# notebooks resolve datasets the same way. It raises on import when the project
# is not configured, so the import is guarded: an unconfigured checkout should
# get setup instructions, not a stack trace.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from warehouse import PROJECT_ID, SNAPSHOT_DATE, marts, q, staging  # noqa: E402
except RuntimeError as exc:
    st.title("📦 Olist Delivery Performance")
    st.error(f"**Not configured yet.** {exc}")
    st.markdown(
        """
Before this dashboard can run:

1. `cp .env.example .env` and fill in `GCP_PROJECT_ID`, `GCS_RAW_BUCKET` and
   `DBT_DEV_DATASET`
2. `gcloud auth application-default login`
3. `make all` — so the marts layer exists to read from

Full instructions: `docs/Module2_Group7_Runbook.pdf`, or run `notebooks/00_runbook.ipynb`.
"""
    )
    st.stop()

NAVY, ACCENT, GOOD, BAD, MUTED = "#1f3864", "#c55a11", "#2e7d32", "#c62828", "#8a8a8a"
REGION_ORDER = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]

# The one place in this app where a metric is expressed in SQL. Mirrors the
# definition in docs/metric_dictionary.md exactly: delivered orders only,
# excluded statuses removed, late means delivered after the promised DATE.
LATE_RATE_SQL = """
    is_delivered
    and not is_excluded_from_kpis
    and delay_vs_promise_days is not null
"""


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=900, show_spinner="Querying BigQuery…")
def run(sql: str) -> pd.DataFrame:
    """Cached query. BigQuery charges by bytes scanned, so repeated interaction
    with the same filters costs nothing after the first call."""
    return q(sql)


@st.cache_data(ttl=900)
def load_filter_options() -> tuple[list[str], list[str]]:
    df = run(f"""
        select distinct year_month
        from {marts('agg_delivery_monthly')}
        where is_in_analysis_window
        order by year_month
    """)
    regions = run(f"""
        select distinct customer_region
        from {marts('dim_customer')}
        where customer_region is not null
        order by customer_region
    """)
    return df.year_month.tolist(), regions.customer_region.tolist()


def where_clause(months: tuple[str, str], regions: list[str], all_regions: list[str]) -> str:
    """Build the shared filter predicate applied to every fct_orders query."""
    clauses = [
        LATE_RATE_SQL.strip(),
        f"format_date('%Y-%m', order_purchase_date) between '{months[0]}' and '{months[1]}'",
    ]
    if regions and set(regions) != set(all_regions):
        quoted = ", ".join(f"'{r}'" for r in regions)
        clauses.append(f"customer_region in ({quoted})")
    return " and ".join(f"({c})" for c in clauses)


def pct(value, digits=1):
    return "—" if pd.isna(value) else f"{value:.{digits}%}"


def count(value):
    """Format an integer measure.

    DataFrame.iloc[0] upcasts an all-numeric row to float64, so counts arrive
    here as floats and a bare ",` format would render "92,345.0".
    """
    return "—" if pd.isna(value) else f"{value:,.0f}"


def money(value):
    return "—" if pd.isna(value) else f"R$ {value:,.0f}"


def money_compact(value):
    """Short money for KPI tiles, which are too narrow for a full figure."""
    if pd.isna(value):
        return "—"
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            return f"R$ {value / limit:,.2f}{suffix}"
    return f"R$ {value:,.0f}"


# st.column_config.NumberColumn does NOT multiply a fraction by 100 for a "%"
# format string -- 0.25 renders as "0.2%". Scale explicitly for table display
# while leaving the underlying fraction untouched for the charts.
def as_percent(df: pd.DataFrame, *columns: str) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out:
            out[column] = out[column] * 100
    return out


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
st.sidebar.title("📦 Olist Delivery")
st.sidebar.caption(f"`{PROJECT_ID}` · marts layer · snapshot {SNAPSHOT_DATE}")

try:
    months, all_regions = load_filter_options()
except Exception as exc:  # noqa: BLE001
    st.error(
        "Could not reach the marts layer.\n\n"
        "Check that `.env` is filled in, that `gcloud auth application-default "
        "login` has been run, and that `make build` has completed at least once."
    )
    st.exception(exc)
    st.stop()

if not months:
    st.error("`agg_delivery_monthly` is empty. Run `make build` first.")
    st.stop()

st.sidebar.subheader("Filters")
month_range = st.sidebar.select_slider(
    "Purchase month",
    options=months,
    value=(months[0], months[-1]),
    help=(
        "Orders are bucketed by PURCHASE month, not delivery month: the question "
        "is 'if I order now, what happens to me?'. Only months inside the usable "
        "coverage window are offered — the sparse first and last months of the "
        "export are excluded so they cannot be read as a demand collapse."
    ),
)
selected_regions = st.sidebar.multiselect(
    "Destination region", all_regions, default=all_regions,
    help="Filters on the customer's region — the destination half of a delivery route.",
)
min_orders = st.sidebar.number_input(
    "Minimum orders to report a rate", min_value=1, max_value=500, value=30, step=10,
    help="A 100% late rate on three orders is noise. Rows below this are hidden from charts.",
)

if not selected_regions:
    st.sidebar.warning("Select at least one region.")
    st.stop()

WHERE = where_clause(month_range, selected_regions, all_regions)

st.sidebar.divider()
st.sidebar.caption(
    "Every figure comes from a tested dbt model in the marts layer. "
    "Definitions: `docs/metric_dictionary.md`."
)


# --------------------------------------------------------------------------- #
# Header + headline KPIs
# --------------------------------------------------------------------------- #
st.title("Where and when are deliveries late?")
st.caption(
    f"Delivered orders purchased between **{month_range[0]}** and **{month_range[1]}** · "
    f"{len(selected_regions)} of {len(all_regions)} regions · "
    "canceled and unavailable orders excluded"
)

headline = run(f"""
    select
        count(*)                                                          as delivered_orders,
        countif(is_late)                                                  as late_orders,
        safe_divide(countif(is_late), count(*))                           as late_rate,
        approx_quantiles(total_delivery_days, 100)[offset(50)]            as median_days,
        approx_quantiles(total_delivery_days, 100)[offset(90)]            as p90_days,
        sum(order_revenue)                                                as revenue,
        sum(late_order_revenue)                                           as late_revenue,
        avg(case when is_late then review_score end)                      as review_late,
        avg(case when not is_late then review_score end)                  as review_on_time,
        avg(promise_slack_days)                                           as promise_slack
    from {marts('fct_orders')}
    where {WHERE}
""").iloc[0]

if headline.delivered_orders == 0:
    st.warning("No delivered orders match these filters.")
    st.stop()

# Secondary figures go in captions, not in `delta`. Streamlit always draws an
# arrow on a delta, and an arrow next to "7.7% of revenue" reads as "revenue
# rose 7.7%", which is not what the number means.
penalty = headline.review_on_time - headline.review_late
tiles = [
    ("Late-delivery rate", pct(headline.late_rate),
     "of delivered orders arrived after the promised date"),
    ("Median delivery time", f"{headline.median_days:.0f} days",
     f"90th percentile: {headline.p90_days:.0f} days"),
    ("Revenue delivered late", money_compact(headline.late_revenue),
     f"{pct(headline.late_revenue / headline.revenue)} of revenue in scope"),
    ("Satisfaction penalty", f"−{penalty:.2f}★",
     f"{headline.review_on_time:.2f}★ on time vs {headline.review_late:.2f}★ late"),
    ("Delivered orders", count(headline.delivered_orders),
     f"{count(headline.late_orders)} of them late"),
]
for column, (label, value, note) in zip(st.columns(5), tiles):
    column.metric(label, value)
    column.caption(note)

st.divider()

tab_where, tab_when, tab_cost, tab_kpi, tab_quality = st.tabs(
    ["📍 Where", "📅 When", "💸 What it costs", "📈 Business KPIs", "✅ Data quality"]
)


# --------------------------------------------------------------------------- #
# WHERE
# --------------------------------------------------------------------------- #
with tab_where:
    st.subheader("Which destinations, and which routes?")
    st.caption(
        "Almost every Olist seller sits in the Southeast, so a distant destination is "
        "really a long route. Origin and destination are shown separately because they "
        "lead to different actions: renegotiate a carrier lane, or recruit sellers closer "
        "to demand."
    )

    by_state = run(f"""
        select
            customer_state,
            customer_region,
            count(*)                                    as delivered_orders,
            countif(is_late)                            as late_orders,
            safe_divide(countif(is_late), count(*))     as late_rate,
            approx_quantiles(total_delivery_days, 100)[offset(50)] as median_days,
            sum(order_revenue)                          as revenue,
            sum(late_order_revenue)                     as late_revenue
        from {marts('fct_orders')}
        where {WHERE}
        group by customer_state, customer_region
        having delivered_orders >= {min_orders}
        order by late_rate desc
    """)

    national = headline.late_rate
    left, right = st.columns([3, 2])

    with left:
        chart = (
            alt.Chart(by_state)
            .mark_bar()
            .encode(
                x=alt.X("customer_state:N", sort="-y", title="destination state"),
                y=alt.Y("late_rate:Q", title="late rate", axis=alt.Axis(format="%")),
                color=alt.Color(
                    "customer_region:N", title="region",
                    scale=alt.Scale(domain=REGION_ORDER,
                                    range=[BAD, ACCENT, MUTED, NAVY, GOOD]),
                ),
                tooltip=[
                    alt.Tooltip("customer_state:N", title="state"),
                    alt.Tooltip("delivered_orders:Q", title="orders", format=","),
                    alt.Tooltip("late_rate:Q", title="late rate", format=".1%"),
                    alt.Tooltip("median_days:Q", title="median days", format=".0f"),
                    alt.Tooltip("revenue:Q", title="revenue", format=",.0f"),
                ],
            )
            .properties(height=340, title="Late-delivery rate by destination state")
        )
        rule = (
            alt.Chart(pd.DataFrame({"y": [national]}))
            .mark_rule(strokeDash=[6, 4], color="black")
            .encode(y="y:Q")
        )
        st.altair_chart(chart + rule, width="stretch")
        st.caption("Dashed line is the overall rate for the current filter.")

    with right:
        st.markdown("**Worst destination states**")
        st.dataframe(
            as_percent(by_state.head(10), "late_rate")[
                ["customer_state", "delivered_orders", "late_rate", "median_days", "revenue"]
            ],
            width="stretch", hide_index=True,
            column_config={
                "customer_state": "state",
                "delivered_orders": st.column_config.NumberColumn("orders", format="%d"),
                "late_rate": st.column_config.NumberColumn("late rate", format="%.1f%%"),
                "median_days": st.column_config.NumberColumn("median days", format="%.0f"),
                "revenue": st.column_config.NumberColumn("revenue", format="R$ %.0f"),
            },
        )

    st.divider()
    st.markdown("#### Origin → destination")

    matrix = run(f"""
        select
            seller_region,
            customer_region,
            count(*)                                as orders,
            safe_divide(countif(is_late), count(*)) as late_rate,
            approx_quantiles(total_delivery_days, 100)[offset(50)] as median_days
        from {marts('fct_orders')}
        where {WHERE} and seller_region is not null
        group by seller_region, customer_region
        having orders >= {min_orders}
    """)

    heat_col, route_col = st.columns([2, 3])
    with heat_col:
        heat = (
            alt.Chart(matrix)
            .mark_rect()
            .encode(
                x=alt.X("customer_region:N", title="destination", sort=REGION_ORDER),
                y=alt.Y("seller_region:N", title="origin", sort=REGION_ORDER),
                color=alt.Color("late_rate:Q", title="late rate",
                                scale=alt.Scale(scheme="oranges"),
                                legend=alt.Legend(format="%")),
                tooltip=[
                    alt.Tooltip("seller_region:N", title="from"),
                    alt.Tooltip("customer_region:N", title="to"),
                    alt.Tooltip("orders:Q", format=","),
                    alt.Tooltip("late_rate:Q", format=".1%"),
                    alt.Tooltip("median_days:Q", title="median days", format=".0f"),
                ],
            )
            .properties(height=300, title="Late rate by region pair")
        )
        labels = heat.mark_text(fontSize=11).encode(
            text=alt.Text("late_rate:Q", format=".0%"),
            color=alt.value("black"),
        )
        st.altair_chart(heat + labels, width="stretch")

    with route_col:
        st.markdown("**Routes carrying the most late orders**")
        routes = run(f"""
            select
                delivery_route,
                count(*)                                as delivered_orders,
                countif(is_late)                        as late_orders,
                safe_divide(countif(is_late), count(*)) as late_rate,
                approx_quantiles(total_delivery_days, 100)[offset(50)] as median_days,
                sum(late_order_revenue)                 as late_revenue
            from {marts('fct_orders')}
            where {WHERE} and seller_state is not null
            group by delivery_route
            having delivered_orders >= {min_orders}
            order by late_orders desc
            limit 15
        """)
        st.dataframe(
            as_percent(routes, "late_rate"), width="stretch", hide_index=True,
            column_config={
                "delivery_route": "route (seller → customer)",
                "delivered_orders": st.column_config.NumberColumn("orders", format="%d"),
                "late_orders": st.column_config.NumberColumn("late", format="%d"),
                "late_rate": st.column_config.NumberColumn("late rate", format="%.1f%%"),
                "median_days": st.column_config.NumberColumn("median days", format="%.0f"),
                "late_revenue": st.column_config.NumberColumn("late revenue", format="R$ %.0f"),
            },
        )
        st.caption(
            "A route uses the order's **primary seller** — the one contributing the most "
            "revenue — so every order belongs to exactly one route and these counts sum "
            "back to the totals. See ADR-004."
        )


# --------------------------------------------------------------------------- #
# WHEN
# --------------------------------------------------------------------------- #
with tab_when:
    st.subheader("Which months, and is it improving?")

    monthly = run(f"""
        select
            year_month,
            month_start_date,
            orders_placed,
            orders_delivered,
            late_orders,
            late_rate,
            median_delivery_days,
            p90_delivery_days,
            median_approval_days,
            median_handover_days,
            median_transit_days,
            avg_review_score,
            late_rate_mom_change
        from {marts('agg_delivery_monthly')}
        where is_in_analysis_window
          and year_month between '{month_range[0]}' and '{month_range[1]}'
        order by month_start_date
    """)
    st.caption(
        "This tab reads `agg_delivery_monthly` directly, so it is unaffected by the "
        "region filter — the model is pre-aggregated at month grain nationally."
    )

    base = alt.Chart(monthly).encode(x=alt.X("year_month:N", title=None, sort=None))
    volume = base.mark_bar(color="#dde3ea").encode(
        y=alt.Y("orders_placed:Q", title="orders placed"),
        tooltip=[alt.Tooltip("year_month:N", title="month"),
                 alt.Tooltip("orders_placed:Q", title="orders", format=",")],
    )
    rate = base.mark_line(color=ACCENT, point=True, strokeWidth=2.5).encode(
        y=alt.Y("late_rate:Q", title="late rate", axis=alt.Axis(format="%")),
        tooltip=[alt.Tooltip("year_month:N", title="month"),
                 alt.Tooltip("late_rate:Q", format=".1%"),
                 alt.Tooltip("median_delivery_days:Q", title="median days")],
    )
    st.altair_chart(
        alt.layer(volume, rate).resolve_scale(y="independent")
        .properties(height=330, title="Order volume and late rate by purchase month"),
        width="stretch",
    )

    if len(monthly) >= 4:
        half = len(monthly) // 2
        first = monthly.head(half)
        second = monthly.tail(half)
        r1 = first.late_orders.sum() / max(first.orders_delivered.sum(), 1)
        r2 = second.late_orders.sum() / max(second.orders_delivered.sum(), 1)
        direction = "improving" if r2 < r1 else "worsening"
        c1, c2, c3 = st.columns(3)
        c1.metric("First half of window", pct(r1))
        c2.metric("Second half", pct(r2), delta=f"{(r2 - r1) * 100:+.1f} pp",
                  delta_color="inverse")
        c3.metric("Trend", direction.title())

    st.divider()
    st.markdown("#### Where do the days actually go?")
    st.caption(
        "Total delivery time split into the three stages we control differently. "
        "These lead to three different recommendations, which is why the model stores "
        "them separately rather than as one number."
    )

    stages = monthly.melt(
        id_vars=["year_month", "month_start_date"],
        value_vars=["median_approval_days", "median_handover_days", "median_transit_days"],
        var_name="stage", value_name="days",
    )
    stages["stage"] = stages["stage"].map({
        "median_approval_days": "1. payment approval",
        "median_handover_days": "2. seller handover",
        "median_transit_days": "3. carrier transit",
    })

    st.altair_chart(
        alt.Chart(stages).mark_area().encode(
            x=alt.X("year_month:N", title=None, sort=None),
            y=alt.Y("days:Q", title="median days", stack="zero"),
            color=alt.Color("stage:N", title="stage",
                            scale=alt.Scale(range=[MUTED, ACCENT, NAVY])),
            tooltip=["year_month:N", "stage:N", alt.Tooltip("days:Q", format=".2f")],
        ).properties(height=300, title="Median days per stage, by purchase month"),
        width="stretch",
    )

    totals = run(f"""
        select
            approx_quantiles(approval_days, 100)[offset(50)]        as approval,
            approx_quantiles(seller_handover_days, 100)[offset(50)] as handover,
            approx_quantiles(carrier_transit_days, 100)[offset(50)] as transit,
            approx_quantiles(total_delivery_days, 100)[offset(50)]  as total
        from {marts('fct_orders')}
        where {WHERE}
    """).iloc[0]

    for col, label, value in zip(
        st.columns(3),
        ["Payment approval", "Seller handover", "Carrier transit"],
        [totals.approval, totals.handover, totals.transit],
    ):
        col.metric(label, f"{value:.2f} days")
        col.caption(f"{pct(value / totals.total)} of total delivery time")


# --------------------------------------------------------------------------- #
# COST
# --------------------------------------------------------------------------- #
with tab_cost:
    st.subheader("What does lateness cost?")

    buckets = run(f"""
        select
            lateness_bucket,
            count(*)                    as orders,
            avg(review_score)           as avg_review_score,
            sum(order_revenue)          as revenue
        from {marts('fct_orders')}
        where {WHERE} and review_score is not null
        group by lateness_bucket
        order by lateness_bucket
    """)

    b = alt.Chart(buckets).encode(alt.X("lateness_bucket:N", title=None, sort=None,
                                        axis=alt.Axis(labelAngle=-35)))
    st.altair_chart(
        alt.layer(
            b.mark_bar(color="#dde3ea").encode(y=alt.Y("orders:Q", title="orders")),
            b.mark_line(color=BAD, point=True, strokeWidth=2.5).encode(
                y=alt.Y("avg_review_score:Q", title="mean review score",
                        scale=alt.Scale(domain=[1, 5])),
                tooltip=["lateness_bucket:N",
                         alt.Tooltip("avg_review_score:Q", format=".2f"),
                         alt.Tooltip("orders:Q", format=",")],
            ),
        ).resolve_scale(y="independent")
        .properties(height=330,
                    title="Review score against how early or late the order arrived"),
        width="stretch",
    )

    st.divider()
    c_left, c_right = st.columns(2)

    with c_left:
        st.markdown("#### Does the penalty survive a control?")
        st.caption(
            "If the pattern only appeared across regions it might just reflect "
            "structurally different logistics. Here it is recomputed *within* each state."
        )
        controlled = run(f"""
            select
                customer_state,
                avg(case when not is_late then review_score end) as on_time,
                avg(case when is_late     then review_score end) as late,
                count(*)                                         as orders
            from {marts('fct_orders')}
            where {WHERE} and review_score is not null
            group by customer_state
            having orders >= {max(min_orders, 100)}
            order by orders desc
            limit 10
        """)
        controlled["penalty"] = controlled.on_time - controlled.late
        st.dataframe(
            controlled[["customer_state", "orders", "on_time", "late", "penalty"]],
            width="stretch", hide_index=True,
            column_config={
                "customer_state": "state",
                "orders": st.column_config.NumberColumn("orders", format="%d"),
                "on_time": st.column_config.NumberColumn("★ on time", format="%.2f"),
                "late": st.column_config.NumberColumn("★ late", format="%.2f"),
                "penalty": st.column_config.NumberColumn("penalty", format="%.2f"),
            },
        )
        st.warning(
            "**Correlation, not causation.** State and product category are controlled; "
            "seller quality and product mix are not. Validate with an A/B or "
            "quasi-experiment before acting at scale.",
            icon="⚠️",
        )

    with c_right:
        st.markdown("#### Revenue exposed to late delivery")
        exposure = run(f"""
            select
                customer_region,
                sum(order_revenue)      as revenue,
                sum(late_order_revenue) as late_revenue,
                safe_divide(sum(late_order_revenue), sum(order_revenue)) as late_share
            from {marts('fct_orders')}
            where {WHERE}
            group by customer_region
            order by late_revenue desc
        """)
        st.altair_chart(
            alt.Chart(exposure).mark_bar(color=BAD).encode(
                y=alt.Y("customer_region:N", title=None, sort="-x"),
                x=alt.X("late_revenue:Q", title="revenue delivered late (R$)"),
                tooltip=["customer_region:N",
                         alt.Tooltip("late_revenue:Q", format=",.0f"),
                         alt.Tooltip("late_share:Q", title="share", format=".1%")],
            ).properties(height=220),
            width="stretch",
        )
        st.metric("Total revenue delivered late", money(exposure.late_revenue.sum()))

    st.divider()
    st.markdown("#### Is the promise wrong, or is delivery slow?")
    st.caption(
        "The cheapest fix here may not be logistics at all. If the promised date is "
        "systematically padded or systematically optimistic, correcting the estimate "
        "costs nothing and changes the customer's experience immediately — which is why "
        "the model stores promise accuracy separately from actual speed."
    )

    p1, p2, p3 = st.columns(3)
    promise = run(f"""
        select
            approx_quantiles(promised_delivery_days, 100)[offset(50)] as promised,
            approx_quantiles(total_delivery_days, 100)[offset(50)]    as actual,
            avg(promise_slack_days)                                   as slack,
            countif(promise_slack_days > 0)                           as early,
            count(*)                                                  as orders
        from {marts('fct_orders')}
        where {WHERE} and promise_slack_days is not null
    """).iloc[0]
    p1.metric("Median promise", f"{promise.promised:.0f} days")
    p2.metric("Median actual", f"{promise.actual:.0f} days")
    p3.metric("Average slack", f"{promise.slack:+.1f} days")
    p3.caption("promise is padded" if promise.slack > 0 else "promise is optimistic")

    dist = run(f"""
        select delay_vs_promise_days as days, count(*) as orders
        from {marts('fct_orders')}
        where {WHERE} and delay_vs_promise_days between -60 and 30
        group by days
        order by days
    """)
    dist["outcome"] = dist.days.apply(lambda d: "late" if d > 0 else "on time or early")
    st.altair_chart(
        alt.Chart(dist).mark_bar().encode(
            x=alt.X("days:Q", title="days relative to the promised date"),
            y=alt.Y("orders:Q", title="orders"),
            color=alt.Color("outcome:N", title=None,
                            scale=alt.Scale(domain=["on time or early", "late"],
                                            range=[GOOD, BAD])),
            tooltip=["days:Q", alt.Tooltip("orders:Q", format=",")],
        ).properties(height=260,
                     title="Distribution of delivery against the promise"),
        width="stretch",
    )


# --------------------------------------------------------------------------- #
# BUSINESS KPIs
# --------------------------------------------------------------------------- #
with tab_kpi:
    st.subheader("The three metrics required by the brief")
    st.caption(
        "Monthly sales, top products and customer segmentation — each cross-read "
        "against delivery, so the story stays one story. These read the pre-aggregated "
        "`agg_*` models, so they are not affected by the region filter."
    )

    st.markdown("#### 1. Monthly sales trend")
    sales = run(f"""
        select
            year_month, month_start_date, revenue, freight, order_count,
            avg_order_value, revenue_mom_growth, late_rate
        from {marts('agg_monthly_sales')}
        where is_in_analysis_window
          and year_month between '{month_range[0]}' and '{month_range[1]}'
        order by month_start_date
    """)

    sb = alt.Chart(sales).encode(alt.X("year_month:N", title=None, sort=None))
    st.altair_chart(
        alt.layer(
            sb.mark_bar(color=NAVY).encode(
                y=alt.Y("revenue:Q", title="revenue (R$)"),
                tooltip=["year_month:N", alt.Tooltip("revenue:Q", format=",.0f"),
                         alt.Tooltip("order_count:Q", title="orders", format=","),
                         alt.Tooltip("avg_order_value:Q", title="AOV", format=",.2f")],
            ),
            sb.mark_line(color=ACCENT, point=True, strokeWidth=2.5).encode(
                y=alt.Y("late_rate:Q", title="late rate", axis=alt.Axis(format="%")),
            ),
        ).resolve_scale(y="independent")
        .properties(height=320,
                    title="Monthly revenue and late rate — do peaks degrade service?"),
        width="stretch",
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Revenue in window", money(sales.revenue.sum()))
    m2.metric("Orders", f"{int(sales.order_count.sum()):,}")
    m3.metric("Average order value",
              money(sales.revenue.sum() / max(sales.order_count.sum(), 1)))
    if len(sales) > 2:
        corr = sales.order_count.corr(sales.late_rate)
        st.caption(
            f"Correlation between monthly order volume and late rate: **{corr:.2f}**. "
            "Positive means peaks strain fulfilment. Descriptive, not causal."
        )

    st.divider()
    st.markdown("#### 2. Top products — revenue, volume and delivery together")
    st.caption(
        "Ranking on revenue alone flatters high-price, low-volume categories. The red "
        "points are top-10 revenue categories with an above-average late rate: where a "
        "logistics fix protects the most money."
    )

    products = run(f"""
        select
            product_category, revenue, units_sold, order_count,
            avg_item_price, late_rate, median_delivery_days,
            avg_review_score, revenue_rank, volume_rank,
            is_high_value_poor_delivery
        from {marts('agg_product_performance')}
        where is_reportable
        order by revenue desc
    """)

    st.altair_chart(
        alt.Chart(products).mark_circle(opacity=0.7).encode(
            x=alt.X("late_rate:Q", title="late rate", axis=alt.Axis(format="%")),
            y=alt.Y("revenue:Q", title="revenue (R$)"),
            size=alt.Size("units_sold:Q", title="units sold",
                          scale=alt.Scale(range=[40, 900])),
            color=alt.Color("is_high_value_poor_delivery:N",
                            title="high value, poor delivery",
                            scale=alt.Scale(domain=[False, True], range=[NAVY, BAD])),
            tooltip=[
                alt.Tooltip("product_category:N", title="category"),
                alt.Tooltip("revenue:Q", format=",.0f"),
                alt.Tooltip("units_sold:Q", format=","),
                alt.Tooltip("late_rate:Q", format=".1%"),
                alt.Tooltip("median_delivery_days:Q", title="median days"),
                alt.Tooltip("avg_review_score:Q", title="★", format=".2f"),
            ],
        ).properties(height=380),
        width="stretch",
    )

    flagged = products[products.is_high_value_poor_delivery]
    if not flagged.empty:
        st.markdown("**Categories that sell well but ship badly**")
        st.dataframe(
            as_percent(flagged, "late_rate")[
                ["product_category", "revenue", "revenue_rank", "units_sold",
                 "late_rate", "median_delivery_days", "avg_review_score"]],
            width="stretch", hide_index=True,
            column_config={
                "product_category": "category",
                "revenue": st.column_config.NumberColumn("revenue", format="R$ %.0f"),
                "revenue_rank": st.column_config.NumberColumn("rev rank", format="%d"),
                "units_sold": st.column_config.NumberColumn("units", format="%d"),
                "late_rate": st.column_config.NumberColumn("late rate", format="%.1f%%"),
                "median_delivery_days": st.column_config.NumberColumn("median days", format="%.0f"),
                "avg_review_score": st.column_config.NumberColumn("★", format="%.2f"),
            },
        )

    st.divider()
    st.markdown("#### 3. Customer segmentation (RFM)")
    st.caption(
        f"Grain is the **person** (`customer_unique_id`), never the per-order "
        f"`customer_id`. Recency is measured against the dataset snapshot date "
        f"({SNAPSHOT_DATE}), never today."
    )

    segments = run(f"""
        select
            rfm_segment,
            count(*)                                  as customers,
            avg(recency_days)                         as avg_recency_days,
            avg(frequency)                            as avg_frequency,
            avg(monetary)                             as avg_monetary,
            sum(monetary)                             as total_revenue,
            avg(late_rate)                            as avg_late_rate,
            countif(is_high_value_with_late_delivery) as at_risk
        from {marts('agg_customer_rfm')}
        group by rfm_segment
        order by rfm_segment
    """)
    segments["revenue_share"] = segments.total_revenue / segments.total_revenue.sum()

    seg_l, seg_r = st.columns(2)
    with seg_l:
        st.altair_chart(
            alt.Chart(segments).mark_bar(color=NAVY).encode(
                y=alt.Y("rfm_segment:N", title=None, sort=None),
                x=alt.X("customers:Q", title="customers"),
                tooltip=["rfm_segment:N", alt.Tooltip("customers:Q", format=",")],
            ).properties(height=260, title="Customers per segment"),
            width="stretch",
        )
    with seg_r:
        st.altair_chart(
            alt.Chart(segments).mark_bar(color=ACCENT).encode(
                y=alt.Y("rfm_segment:N", title=None, sort=None),
                x=alt.X("revenue_share:Q", title="share of revenue",
                        axis=alt.Axis(format="%")),
                tooltip=["rfm_segment:N", alt.Tooltip("revenue_share:Q", format=".1%"),
                         alt.Tooltip("total_revenue:Q", format=",.0f")],
            ).properties(height=260, title="Share of revenue per segment"),
            width="stretch",
        )

    at_risk = run(f"""
        select
            countif(is_high_value_with_late_delivery) as customers,
            sum(case when is_high_value_with_late_delivery then monetary end) as revenue,
            safe_divide(
                sum(case when is_high_value_with_late_delivery then monetary end),
                sum(monetary)
            ) as share
        from {marts('agg_customer_rfm')}
    """).iloc[0]

    st.info(
        f"**{int(at_risk.customers):,} high-value customers have experienced a late "
        f"delivery**, representing {money(at_risk.revenue)} — {pct(at_risk.share)} of all "
        "customer revenue. This is the number that turns a logistics metric into a "
        "retention budget.",
        icon="🎯",
    )


# --------------------------------------------------------------------------- #
# DATA QUALITY
# --------------------------------------------------------------------------- #
with tab_quality:
    st.subheader("Can these numbers be trusted?")
    st.caption(
        "A dashboard is only as credible as the pipeline behind it. These checks run "
        "live against the warehouse, and they are the same assertions the dbt build "
        "enforces on every run."
    )

    recon = run(f"""
        select
            (select round(sum(item_price), 2) from {staging('stg_order_items')})  as staging_revenue,
            (select round(sum(item_price), 2) from {marts('fct_order_items')})    as fact_item_revenue,
            (select round(sum(order_revenue), 2) from {marts('fct_orders')})      as fact_order_revenue,
            (select count(distinct order_id) from {staging('stg_orders')})        as staging_orders,
            (select count(*) from {marts('fct_orders')})                          as fact_order_rows,
            (select count(*) from {marts('dim_customer')})                        as dim_customers,
            (select count(*) from {marts('agg_customer_rfm')})                    as rfm_rows
    """).iloc[0]

    revenue_ok = recon.staging_revenue == recon.fact_item_revenue == recon.fact_order_revenue
    orders_ok = recon.staging_orders == recon.fact_order_rows
    rfm_ok = recon.dim_customers == recon.rfm_rows

    # The dashboard recomputes the late rate against fct_orders in order to support
    # interactive filtering. This proves that recomputation still agrees with the
    # pre-aggregated model, so the app cannot silently drift from the pipeline.
    agg_rate = run(f"""
        select safe_divide(sum(late_orders), sum(orders_delivered)) as late_rate
        from {marts('agg_delivery_monthly')}
        where is_in_analysis_window
    """).iloc[0].late_rate
    app_rate = run(f"""
        select safe_divide(countif(is_late), count(*)) as late_rate
        from {marts('fct_orders')}
        where {LATE_RATE_SQL.strip()}
          and order_purchase_date between date('2016-09-01') and date('2018-10-31')
    """).iloc[0].late_rate
    rate_ok = abs(agg_rate - app_rate) < 1e-4

    checks = pd.DataFrame([
        {"check": "Revenue reconciles: staging = fct_order_items = fct_orders",
         "ok": revenue_ok,
         "detail": f"{recon.staging_revenue:,.2f} / {recon.fact_item_revenue:,.2f} / {recon.fact_order_revenue:,.2f}"},
        {"check": "fct_orders is at one row per order",
         "ok": orders_ok,
         "detail": f"{count(recon.staging_orders)} staging orders / {count(recon.fact_order_rows)} fact rows"},
        {"check": "RFM is keyed on the person, not the per-order id",
         "ok": rfm_ok,
         "detail": f"{count(recon.dim_customers)} customers / {count(recon.rfm_rows)} RFM rows"},
        {"check": "This dashboard's late rate agrees with agg_delivery_monthly",
         "ok": rate_ok,
         "detail": f"app {app_rate:.4%} vs model {agg_rate:.4%}"},
    ])

    # Rendered as markdown rather than st.dataframe on purpose: the data grid
    # sizes its columns to content and collapses a four-row status readout into
    # something unreadable. A grid is for exploring data; this is a verdict.
    st.markdown(
        "| | Check | Observed |\n|:--:|---|---|\n"
        + "\n".join(
            f"| {'✅' if row.ok else '❌'} | {row.check} | `{row.detail}` |"
            for row in checks.itertuples()
        )
    )

    if checks.ok.all():
        st.success(
            "All live checks pass. Revenue is not inflated by any join, the fact table "
            "is at its declared grain, segmentation is at person grain, and this app's "
            "numbers match the tested models.",
            icon="✅",
        )
    else:
        st.error(
            "A reconciliation check failed. Do not present these figures — investigate "
            "with `make build` and read the failing dbt test first.",
            icon="🚨",
        )

    st.divider()
    st.markdown("#### What the pipeline enforces on every build")
    st.markdown(
        """
| Gate | Tool | Blocks |
|---|---|---|
| **1 — File validation** | Great Expectations, before load | Column set, row count vs manifest, non-null keys, money ranges, categorical domains. A malformed export never reaches BigQuery. |
| **2 — Model contracts** | dbt, 161 tests | Uniqueness, referential integrity, accepted values, numeric ranges, milestone chronology, delivery-measure validity, source-to-mart reconciliation. |

Severity is assigned deliberately: **error** blocks publication, **warn** publishes
with an explanation (voucher payments legitimately break the payment-total identity,
so making that an error would produce a permanently red build everyone ignores).

Full definitions: `docs/metric_dictionary.md` · decisions: `docs/adr/`
"""
    )

    with st.expander("Known limitations — read before quoting any figure"):
        st.markdown(
            f"""
- **Static export**, September 2016 – October 2018. Recency is measured against
  {SNAPSHOT_DATE}, not today. There is no genuine freshness dimension.
- **Sparse edge months** are excluded from the month selector, so a partial month
  cannot be mistaken for a demand collapse.
- **Correlation, not causation.** Late delivery is *associated* with lower review
  scores; state and category are controlled, seller quality and product mix are not.
- **No cost data**, so margin cannot be computed. Every recommendation is framed on
  revenue and satisfaction, never on profit.
- **Multi-seller orders** are attributed to the primary seller for route analysis.
- **Voucher payments** legitimately break the payment-total identity; tested at warn
  severity and reported openly rather than coerced.
"""
        )

st.divider()
st.caption(
    "Big Data Module 2 · Group 7 · Olist delivery performance · "
    "every figure sourced from the tested marts layer"
)
