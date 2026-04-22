"""
dashboard/app.py
================
The main Streamlit dashboard for the Market Gap Analysis project.

Run with:
    streamlit run dashboard/app.py

How Streamlit works (for beginners):
    1. This script runs TOP TO BOTTOM every time the user interacts.
    2. st.sidebar.*  → renders stuff in the left sidebar.
    3. st.columns()  → creates side-by-side layout columns.
    4. st.metric()   → renders a nice KPI card.
    5. st.plotly_chart() → renders a Plotly figure.
    6. @st.cache_data prevents data from being reloaded on every interaction.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Import our data engine ───────────────────────────────────────────────────
from utils.data_loader import (
    load_snack_data,
    get_full_yearly_counts,
    get_category_stats,
    get_gap_analysis,
    get_demand_signal,
    get_bodi,
    get_protein_sources,
    get_nova_breakdown,
    NHS_PROTEIN_THRESHOLD,
    NHS_SUGAR_THRESHOLD,
)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG — must be the FIRST Streamlit command
# ═════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Sugar Trap — Market Gap Analysis",
    page_icon="🎯",
    layout="wide",            # use the full browser width
    initial_sidebar_state="expanded",
)

# ═════════════════════════════════════════════════════════════════════════════
# LOAD DATA (cached — runs only once)
# ═════════════════════════════════════════════════════════════════════════════
df_snacks = load_snack_data()

# Pre-compute all analysis tables
yearly_counts  = get_full_yearly_counts()   # full clean dataset, not just snacks
category_stats = get_category_stats(df_snacks)
gap_df         = get_gap_analysis(df_snacks)
demand_df      = get_demand_signal(df_snacks)
bodi_df        = get_bodi(gap_df, demand_df)
protein_df     = get_protein_sources(df_snacks)
nova_df        = get_nova_breakdown(df_snacks)

# ═════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Filters & Controls
# ═════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.image("https://img.icons8.com/emoji/96/bar-chart-emoji.png", width=60)
    st.title("🎯 Sugar Trap")
    st.caption("Market Gap Analysis Dashboard")
    st.divider()

    # Category filter (required by Story 3: "Allow the user to filter
    # the chart by the High Level Categories you created in Story 2.")
    all_categories = sorted(
        df_snacks["primary_category"].dropna().unique().tolist()
    )
    category_options = ["All Categories"] + all_categories

    selected_view = st.selectbox(
        "🔍 Focus on a Category",
        options=category_options,
        index=0,
        help="Select a single category to deep-dive, or 'All' for the full view.",
    )

    # Show how many products are in the selected view
    if selected_view == "All Categories":
        selected_categories = all_categories
        st.caption(f"Showing all **{len(df_snacks):,}** snack products")
    else:
        selected_categories = [selected_view]
        count = len(df_snacks[df_snacks["primary_category"] == selected_view])
        st.caption(f"Showing **{count:,}** products in *{selected_view}*")

    st.divider()
    st.markdown("**Health Thresholds (NHS/WHO)**")
    st.markdown(f"- Protein > **{NHS_PROTEIN_THRESHOLD}g** / 100g")
    st.markdown(f"- Sugar < **{NHS_SUGAR_THRESHOLD}g** / 100g")
    st.markdown("- Nutri-Score **A** or **B**")

    st.divider()
    st.markdown(
        "Built with [Streamlit](https://streamlit.io) · "
        "Data from [OpenFoodFacts](https://world.openfoodfacts.org)"
    )

# Apply the sidebar filter
df_filtered = df_snacks[
    df_snacks["primary_category"].isin(selected_categories)
]

# ═════════════════════════════════════════════════════════════════════════════
# HEADER
# ═════════════════════════════════════════════════════════════════════════════
st.title("🎯 The \"Sugar Trap\" — Market Gap Analysis")
st.markdown(
    "Identifying the **Blue Ocean** in the snack aisle: "
    "where consumer demand for healthy snacks is *not* being met by current products."
)

# ── KPI cards across the top ─────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)

total_snacks  = len(df_filtered)
healthy_count = int(df_filtered["is_healthy"].sum())
healthy_pct   = (healthy_count / total_snacks * 100) if total_snacks > 0 else 0
num_cats      = df_filtered["primary_category"].nunique()

# The top BODI winner
top_bodi = bodi_df.iloc[0] if len(bodi_df) > 0 else None

k1.metric("Total Snack Products",  f"{total_snacks:,}")
k2.metric("Truly Healthy",         f"{healthy_count:,}", f"{healthy_pct:.1f}%")
k3.metric("Categories Analysed",   num_cats)
if top_bodi is not None:
    k4.metric("🏆 Top BODI Category", top_bodi["primary_category"])

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Data Freshness (dynamic median-year cutoff)
# ═════════════════════════════════════════════════════════════════════════════

# Compute the cutoff dynamically: use the median year of the dataset.
# This is the most statistically defensible approach — no hardcoded year.
all_years = yearly_counts.index.astype(int)
total_count = yearly_counts.sum()

# Build a cumulative sum to find the median year
cumulative = yearly_counts.cumsum()
median_year = int(cumulative[cumulative >= total_count / 2].index[0])

# Count products from the median year onwards
recent_count = yearly_counts[yearly_counts.index >= median_year].sum()
recent_pct   = (recent_count / total_count) * 100

st.header("📅 Data Freshness")
st.caption(
    f"The median contribution year is **{median_year}**. "
    f"**{recent_pct:.1f}%** of the database was added from {median_year} onwards, "
    f"proving the insights reflect modern consumer trends."
)

colors = [
    "#f97316" if int(y) >= median_year else "#6366f1"
    for y in yearly_counts.index
]

fig_years = go.Figure(
    go.Bar(
        x=yearly_counts.index.astype(int),
        y=yearly_counts.values,
        marker_color=colors,
        text=[f"{v:,}" for v in yearly_counts.values],
        textposition="outside",
    )
)
fig_years.add_annotation(
    x=0.02, y=0.95, xref="paper", yref="paper",
    text=f"🔥 {recent_pct:.1f}% added since {median_year} (median year)",
    showarrow=False,
    font=dict(size=14, color="#f97316"),
    bgcolor="white", bordercolor="#f97316", borderwidth=1.5,
    borderpad=6,
)
fig_years.update_layout(
    xaxis_title="Year", yaxis_title="# Products",
    height=380, margin=dict(t=30, b=40),
    plot_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig_years, width="stretch")

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Nutrient Matrix Scatter Plot (Story 3)
# ═════════════════════════════════════════════════════════════════════════════
st.header("🔬 Nutrient Matrix: Sugar vs. Protein")
st.caption(
    "Each bubble is a snack category. The **bottom-right quadrant** (High Protein, Low Sugar) "
    "is the Blue Ocean — the market gap our client should exploit."
)

stats_filtered = category_stats[
    category_stats["primary_category"].isin(selected_categories)
]

fig_scatter = px.scatter(
    stats_filtered,
    x="median_sugar",
    y="median_protein",
    color="primary_category",
    size="product_count",
    hover_data={
        "median_fat":   ":.1f",
        "median_fiber":  ":.1f",
        "product_count": ":,",
    },
    labels={
        "median_sugar":   "Median Sugar (g/100g)",
        "median_protein": "Median Protein (g/100g)",
        "primary_category": "Snack Category",
    },
    text="primary_category",
)
fig_scatter.update_traces(textposition="top center", textfont_size=10)

# NHS threshold lines
fig_scatter.add_hline(
    y=NHS_PROTEIN_THRESHOLD,
    line_dash="dash", line_color="green", line_width=1,
    annotation_text="High-protein threshold",
    annotation_position="top right",
)
fig_scatter.add_vline(
    x=NHS_SUGAR_THRESHOLD,
    line_dash="dash", line_color="red", line_width=1,
    annotation_text="Low-sugar threshold",
    annotation_position="top right",
)

# Blue Ocean annotation
fig_scatter.add_annotation(
    x=1.5, y=9,
    text="🎯 Blue Ocean<br>(High Protein, Low Sugar)",
    showarrow=False,
    font=dict(color="green", size=12),
    bgcolor="rgba(0,200,100,0.15)",
    bordercolor="green", borderwidth=1,
)

fig_scatter.update_layout(
    height=550,
    showlegend=False,
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=30),
)
st.plotly_chart(fig_scatter, width="stretch")

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Supply Gap + Demand Signal (side by side)
# ═════════════════════════════════════════════════════════════════════════════
st.header("📊 Supply Gap vs. Demand Signal")

col_gap, col_demand = st.columns(2)

with col_gap:
    st.subheader("Supply Gap (Opportunity Score)")
    st.caption(
        "How many products in each category **fail** the strict health test? "
        "Higher = bigger gap = bigger opportunity."
    )
    st.dataframe(
        gap_df[["primary_category", "total_products", "gap_pct_missing", "opportunity_score_pct"]]
        .rename(columns={
            "primary_category":      "Category",
            "total_products":        "Products",
            "gap_pct_missing":       "% Unhealthy",
            "opportunity_score_pct": "Opportunity Score",
        })
        .style.format({
            "Products": "{:,.0f}",
            "% Unhealthy": "{:.1%}",
            "Opportunity Score": "{:.1f}",
        })
        .background_gradient(subset=["Opportunity Score"], cmap="YlOrRd"),
        width="stretch",
        hide_index=True,
    )

with col_demand:
    st.subheader("Demand Signal (Health Labels)")
    st.caption(
        "What % of products carry health marketing badges like "
        "\"High Protein\" or \"No Added Sugar\"? Higher = consumers want health."
    )
    st.dataframe(
        demand_df[["primary_category", "total_products", "pct_marketing_health"]]
        .rename(columns={
            "primary_category":    "Category",
            "total_products":      "Products",
            "pct_marketing_health": "% Marketing Health",
        })
        .style.format({
            "Products": "{:,.0f}",
            "% Marketing Health": "{:.1f}%",
        })
        .background_gradient(subset=["% Marketing Health"], cmap="YlGn"),
        width="stretch",
        hide_index=True,
    )

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4 — BODI Ranking (the punchline)
# ═════════════════════════════════════════════════════════════════════════════
st.header("🏆 Blue Ocean Disruption Index (BODI)")
st.caption(
    "**BODI = √(Supply Gap × Demand)**. Categories only rank high if "
    "**both** the market gap AND consumer demand are simultaneously large."
)

col_table, col_chart = st.columns([1, 1])

with col_table:
    st.dataframe(
        bodi_df[["primary_category", "total_products", "norm_supply_gap", "norm_demand", "blue_ocean_index"]]
        .rename(columns={
            "primary_category":  "Category",
            "total_products":    "Products",
            "norm_supply_gap":   "Supply Gap (0-100)",
            "norm_demand":       "Demand (0-100)",
            "blue_ocean_index":  "BODI Score",
        })
        .style.format({
            "Products": "{:,.0f}",
            "Supply Gap (0-100)": "{:.1f}",
            "Demand (0-100)": "{:.1f}",
            "BODI Score": "{:.1f}",
        })
        .background_gradient(subset=["BODI Score"], cmap="RdYlGn"),
        width="stretch",
        hide_index=True,
    )

with col_chart:
    fig_bodi = px.bar(
        bodi_df,
        x="blue_ocean_index",
        y="primary_category",
        orientation="h",
        color="blue_ocean_index",
        color_continuous_scale="RdYlGn",
        labels={
            "blue_ocean_index": "BODI Score",
            "primary_category": "",
        },
        text="blue_ocean_index",
    )
    fig_bodi.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    fig_bodi.update_layout(
        height=400,
        yaxis=dict(autorange="reversed"),
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(l=10, r=60, t=10, b=30),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_bodi, width="stretch")

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Key Insight / Recommendation box (Story 4)
# ═════════════════════════════════════════════════════════════════════════════
st.header("💡 Key Insight — The Recommendation")

if top_bodi is not None:
    runner_up = bodi_df.iloc[1]["primary_category"] if len(bodi_df) > 1 else "N/A"

    st.success(
        f"**Based on the data, the biggest market opportunity is in "
        f"*{top_bodi['primary_category']}* (BODI {top_bodi['blue_ocean_index']:.1f}), "
        f"closely followed by *{runner_up}*.**\n\n"
        f"Specifically, target products with > **{NHS_PROTEIN_THRESHOLD}g** protein "
        f"and < **{NHS_SUGAR_THRESHOLD}g** sugar per 100g. "
        f"Cross-validating with Nutri-Score (A/B) ensures the recommendation avoids "
        f"high-fat, high-salt \"health-washed\" products.\n\n"
        f"💡 *Creative recommendation:* combine the top two categories — "
        f"e.g., a **Healthy Chocolate-Coated Protein Biscuit** — "
        f"to capture both segments simultaneously."
    )
else:
    st.warning("No BODI data available. Check your clean CSV.")

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Hidden Gem: Protein Sources (Story 5)
# ═════════════════════════════════════════════════════════════════════════════
st.header("🔍 The Hidden Gem — Top Protein Sources")
st.caption(
    "What ingredients are driving the high-protein content in the products "
    "that actually **pass** our strict health check? "
    "This tells the R&D team *what to put in the recipe*."
)

col_ps_table, col_ps_chart = st.columns([1, 1])

with col_ps_table:
    st.dataframe(protein_df, width="stretch", hide_index=True)

with col_ps_chart:
    if len(protein_df) > 0:
        fig_protein = px.bar(
            protein_df.head(7),
            x="% of Healthy Snacks",
            y="Protein Source",
            orientation="h",
            color="% of Healthy Snacks",
            color_continuous_scale="Tealgrn",
            text="% of Healthy Snacks",
        )
        fig_protein.update_traces(
            texttemplate="%{text:.1f}%", textposition="outside"
        )
        fig_protein.update_layout(
            height=350,
            yaxis=dict(autorange="reversed"),
            showlegend=False,
            coloraxis_showscale=False,
            margin=dict(l=10, r=60, t=10, b=30),
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_protein, width="stretch")

st.divider()

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Clean Label Vulnerability (Story 6 — Candidate's Choice)
# ═════════════════════════════════════════════════════════════════════════════
st.header("🧪 Candidate's Choice: The Clean Label Vulnerability Index")
st.caption(
    "**Why we added this:** Hitting macro targets was the 2010s trend. "
    "The 2020s trend is *Clean Label* — avoiding ultra-processed foods (UPFs). "
    "If 90%+ of \"healthy\" competitors are NOVA 4 (ultra-processed), "
    "our client can disrupt by formulating a NOVA 3 (clean) recipe."
)

col_nova_chart, col_nova_text = st.columns([1, 1])

with col_nova_chart:
    if len(nova_df) > 0:
        color_map = {
            "NOVA 1 — Unprocessed whole foods":            "#2E7D32",
            "NOVA 2 — Processed culinary ingredients":     "#81C784",
            "NOVA 3 — Processed foods (acceptable)":       "#F9A825",
            "NOVA 4 — Ultra-processed (⚠️ chemicals)":    "#C62828",
        }
        fig_nova = px.pie(
            nova_df,
            values="% of Healthy Snacks",
            names="Processing Level",
            hole=0.4,
            color="Processing Level",
            color_discrete_map=color_map,
        )
        fig_nova.update_traces(
            textposition="inside", textinfo="percent+label"
        )
        fig_nova.update_layout(
            height=400,
            showlegend=False,
            margin=dict(t=10, b=10),
        )
        st.plotly_chart(fig_nova, width="stretch")

with col_nova_text:
    nova4_pct = nova_df.loc[
        nova_df["Processing Level"].str.contains("NOVA 4", na=False),
        "% of Healthy Snacks"
    ]
    nova4_val = nova4_pct.values[0] if len(nova4_pct) > 0 else 0

    st.metric("Ultra-Processed (NOVA 4)", f"{nova4_val:.1f}%")
    st.markdown(
        f"**{nova4_val:.0f}%** of the snacks that *passed* our strict health "
        f"thresholds are still classified as **Ultra-Processed** (NOVA 4). "
        f"This means they rely on chemical emulsifiers, protein isolates, "
        f"and artificial sweeteners to achieve their macros."
    )
    st.info(
        "**The Disruption:** Our client should formulate using a **NOVA 3** "
        "(processed but not ultra-processed) recipe. This captures the "
        "growing 'Clean Label' premium market segment that competitors "
        "cannot reach with their current NOVA 4 formulations."
    )

# ═════════════════════════════════════════════════════════════════════════════
# FOOTER
# ═════════════════════════════════════════════════════════════════════════════
st.divider()
st.markdown(
    "<div style='text-align: center; color: #888; font-size: 0.85em;'>"
    "Sugar Trap Market Gap Analysis · Helix CPG Partners · "
    "Powered by OpenFoodFacts · Built with Streamlit"
    "</div>",
    unsafe_allow_html=True,
)
