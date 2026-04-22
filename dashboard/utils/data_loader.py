"""
dashboard/utils/data_loader.py
================================
The engine room of the dashboard.

Loads the pre-cleaned CSV, runs all analysis computations ONCE,
and caches everything using Streamlit's @st.cache_data decorator.
The main app.py imports everything from here — it never touches raw data.
"""
import re
import numpy as np
import pandas as pd
import streamlit as st


# ── Path to the cleaned dataset (relative to project root) ───────────────────
# Try compressed first (for Streamlit Cloud), fall back to uncompressed (local)
import os
CLEAN_CSV = (
    "data/openfoodfacts_clean.csv.gz"
    if os.path.exists("data/openfoodfacts_clean.csv.gz")
    else "data/openfoodfacts_clean.csv"
)

# ── NHS / WHO Health Thresholds ───────────────────────────────────────────────
NHS_PROTEIN_THRESHOLD = 5.0   # g/100g — above this = "high protein"
NHS_SUGAR_THRESHOLD   = 5.0   # g/100g — below this = "low sugar"

# ── Snack taxonomy: multi-lingual keyword map ─────────────────────────────────
SNACK_SUBCATEGORY_MAP = {
    "Protein Bars & Supplements": [
        "protein", "whey", "fitness", "sport", "energie", "energy"
    ],
    "Nuts, Seeds & Trail Mix": [
        "nut", "seed", "trail mix", "almond", "cashew", "peanut",
        "pistachio", "walnut", "amande", "noisette", "cacahuete",
        "nuss", "almendra", "erdnuss", "frutos-secos",
    ],
    "Chips & Crisps": [
        "chip", "crisp", "popcorn", "pretzel", "puff", "tortilla",
        "corn snack", "nacho", "patatas", "patatine", "frites",
        "croustilles", "bretzel", "palomitas", "salty snack",
        "appetizer", "snack sale",
    ],
    "Pastries, Cakes & Sweet Breads": [
        "cake", "pastr", "panettone", "croissant", "colomba", "pandoro",
        "brioche", "muffin", "waffle", "donut", "doughnut", "milk bread",
        "palmier", "viennois",
    ],
    "Cookies & Biscuits": [
        "cookie", "biscuit", "wafer", "shortbread", "digestive", "graham",
        "macaron", "galleta", "biscotti", "keks", "gebäck", "gaufre",
        "ciastka", "sable", "madeleine", "brownie", "gingerbread",
        "snacks sucre",
    ],
    "Chocolate & Confections": [
        "chocolate", "cand", "sweet", "confection", "caramel", "fudge",
        "gumm", "jelly", "bonbon", "gum", "chocolat", "schoko",
        "cioccolato", "ciocolata", "czekolada", "dulce", "caramelle",
        "nougat", "turrón", "turron", "marshmallow", "lollipop",
        "praline", "truffle", "liquorice", "dragee", "dragée",
        "easter egg", "turkish delight", "marzipan", "halva",
    ],
    "Cereal & Granola Bars": [
        "granola", "cereal", "oat", "muesli", "rice bar", "flapjack",
        "barres", "bars",
    ],
    "Crackers & Rice Cakes": [
        "cracker", "rice cake", "breadstick", "rusk", "crispbread",
        "galette", "grissini", "crackers", "taralli", "gressin",
    ],
    "Fruit Snacks & Dried Fruit": [
        "fruit", "raisin", "date", "apricot", "fig", "compote",
        "frucht", "frutta", "pomme",
    ],
}

# ── Demand proxy: health label keywords ───────────────────────────────────────
HEALTH_LABELS = [
    "high-protein", "low-sugar", "no-added-sugar", "high-fibre",
    "organic", "low-fat", "vegan", "gluten-free", "keto",
    "low-calorie", "sugar-free", "reduced-fat", "source-of-protein",
]

# ── Protein source ingredient keywords ───────────────────────────────────────
PROTEIN_SOURCES = {
    "Whey / Dairy": ["whey", "milk protein", "casein", "lactoserum"],
    "Soy":          ["soy", "soya"],
    "Pea":          ["pea protein", "pois"],
    "Peanuts":      ["peanut", "cacahuete", "arachide"],
    "Almonds":      ["almond", "amande"],
    "Oats":         ["oat", "avoine"],
    "Hemp / Chia":  ["hemp", "chia", "flax", "pumpkin seed", "sunflower seed"],
}


# ═════════════════════════════════════════════════════════════════════════════
# 1. Load & categorise
# ═════════════════════════════════════════════════════════════════════════════

def _assign_subcategory(main_cat: str) -> str:
    """Map a raw main_category_en value to one of our 9 strategic buckets."""
    if not isinstance(main_cat, str):
        return "Other Snacks"
    cat_clean = re.sub(r"^[a-z]{2}:", "", str(main_cat).lower()).replace("-", " ")
    for bucket, keywords in SNACK_SUBCATEGORY_MAP.items():
        if any(kw in cat_clean for kw in keywords):
            return bucket
    return "Other Snacks"


@st.cache_data(show_spinner="Loading & categorising snack data…")
def load_snack_data() -> pd.DataFrame:
    """
    Load the pre-cleaned CSV, filter to snacks only, and assign
    primary_category. Result is cached so this only runs once per session.

    Returns
    -------
    pd.DataFrame
        Snack-only rows with a `primary_category` column added.
    """
    df = pd.read_csv(CLEAN_CSV, low_memory=False)

    # Parse the nutriscore_grade as an ordered category (a < b < c < d < e)
    grade_order = pd.CategoricalDtype(
        categories=["a", "b", "c", "d", "e"], ordered=True
    )
    if "nutriscore_grade" in df.columns:
        df["nutriscore_grade"] = (
            df["nutriscore_grade"].str.lower().astype(grade_order)
        )

    # Parse nova_group as nullable integer
    if "nova_group" in df.columns:
        df["nova_group"] = pd.to_numeric(df["nova_group"], errors="coerce").astype("Int64")

    # ── Filter to official snack products ────────────────────────────────────
    # We check categories_tags (the full hierarchy) for the en:snacks tag.
    # This is safer than checking main_category_en, which is only the leaf node.
    df_snacks = df[
        df["categories_tags"]
        .fillna("")
        .str.contains(r"\ben:snacks\b", regex=True)
    ].copy()

    # ── Assign our 9 strategic categories ────────────────────────────────────
    df_snacks["primary_category"] = df_snacks["main_category_en"].apply(
        _assign_subcategory
    )

    # ── Health flag: NHS/WHO + Nutri-Score dual validation ───────────────────
    high_protein = df_snacks["proteins_100g"] > NHS_PROTEIN_THRESHOLD
    low_sugar    = df_snacks["sugars_100g"]   < NHS_SUGAR_THRESHOLD
    good_grade   = df_snacks["nutriscore_grade"].isin(["a", "b"]) if "nutriscore_grade" in df_snacks.columns else True

    df_snacks["is_healthy"] = high_protein & low_sugar & good_grade

    return df_snacks


# ═════════════════════════════════════════════════════════════════════════════
# 2. Analysis computations (all cached separately)
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False)
def get_yearly_counts(_df: pd.DataFrame) -> pd.Series:
    """Returns product count per creation year (for a given DataFrame)."""
    years = pd.to_datetime(_df["created_datetime"], errors="coerce", utc=True).dt.year
    return years.value_counts().sort_index()


@st.cache_data(show_spinner="Loading full dataset for freshness chart…")
def get_full_yearly_counts() -> pd.Series:
    """
    Load the FULL clean CSV (all food products, not just snacks)
    and return product counts per year.

    This is used for the Data Freshness chart, which should reflect
    the entire database — not just the snack subset.
    """
    df_full = pd.read_csv(CLEAN_CSV, usecols=["created_datetime"], low_memory=False)
    years = pd.to_datetime(df_full["created_datetime"], errors="coerce", utc=True).dt.year
    return years.value_counts().sort_index()


@st.cache_data(show_spinner=False)
def get_category_stats(_df: pd.DataFrame) -> pd.DataFrame:
    """Median nutritional stats per primary_category."""
    return (
        _df.groupby("primary_category")
        .agg(
            median_sugar   =("sugars_100g",   "median"),
            median_protein =("proteins_100g", "median"),
            median_fat     =("fat_100g",      "median"),
            median_fiber   =("fiber_100g",    "median"),
            product_count  =("code",          "count"),
        )
        .reset_index()
        .dropna(subset=["median_sugar", "median_protein"])
    )


@st.cache_data(show_spinner=False)
def get_gap_analysis(_df: pd.DataFrame) -> pd.DataFrame:
    """
    Gap Analysis: for each category, how many products fail the health check?

    Columns returned:
        primary_category, total_products, healthy_products,
        gap_pct_missing, absolute_gap, opportunity_score_pct
    """
    gap = (
        _df.groupby("primary_category")
        .agg(
            total_products   =("code",       "count"),
            healthy_products =("is_healthy", "sum"),
        )
        .reset_index()
    )
    gap = gap[gap["total_products"] >= 500]   # ignore tiny/unreliable categories
    gap["gap_pct_missing"] = 1 - (gap["healthy_products"] / gap["total_products"])
    gap["absolute_gap"]    = gap["gap_pct_missing"] * np.sqrt(gap["total_products"])

    max_gap = gap["absolute_gap"].max()
    gap["opportunity_score_pct"] = (gap["absolute_gap"] / max_gap) * 100

    return gap.sort_values("opportunity_score_pct", ascending=False)


@st.cache_data(show_spinner=False)
def get_demand_signal(_df: pd.DataFrame) -> pd.DataFrame:
    """
    Demand proxy: % of products in each category using health marketing labels.
    """
    def _count_labels(s):
        if not isinstance(s, str):
            return 0
        lo = s.lower()
        return sum(kw in lo for kw in HEALTH_LABELS)

    df = _df.copy()
    df["health_label_count"] = df["labels_tags"].apply(_count_labels)

    demand = (
        df[df["primary_category"] != "Other Snacks"]
        .groupby("primary_category")
        .agg(
            total_products           =("code",              "count"),
            products_marketing_health=("health_label_count", lambda x: (x > 0).sum()),
            pct_marketing_health     =("health_label_count", lambda x: (x > 0).mean() * 100),
        )
        .sort_values("pct_marketing_health", ascending=False)
        .round(1)
        .reset_index()
    )
    return demand


@st.cache_data(show_spinner=False)
def get_bodi(_gap: pd.DataFrame, _demand: pd.DataFrame) -> pd.DataFrame:
    """
    Blue Ocean Disruption Index (BODI).

    BODI = sqrt(norm_supply_gap × norm_demand)

    Both axes are normalised to 0-100 first so neither dominates.
    The geometric mean means a category ONLY scores high if BOTH
    the supply gap AND consumer demand are simultaneously high.
    """
    merged = pd.merge(
        _gap[["primary_category", "opportunity_score_pct", "total_products"]],
        _demand[["primary_category", "pct_marketing_health"]],
        on="primary_category",
    )
    merged["norm_supply_gap"] = merged["opportunity_score_pct"]
    merged["norm_demand"]     = (
        merged["pct_marketing_health"] / merged["pct_marketing_health"].max()
    ) * 100

    vulnerability = merged["norm_supply_gap"] * merged["norm_demand"]
    merged["blue_ocean_index"] = np.sqrt(vulnerability).round(1)

    return merged.sort_values("blue_ocean_index", ascending=False)


@st.cache_data(show_spinner=False)
def get_protein_sources(_df: pd.DataFrame) -> pd.DataFrame:
    """
    For the healthy snacks only, extract the most common protein sources
    from ingredients_tags / ingredients_text.
    """
    df_healthy = _df[_df["is_healthy"] == True].copy()

    target_col = (
        "ingredients_tags"
        if "ingredients_tags" in df_healthy.columns
        else "ingredients_text"
    )

    def _find_sources(s):
        if not isinstance(s, str):
            return []
        lo = s.lower()
        return [
            group
            for group, kws in PROTEIN_SOURCES.items()
            if any(kw in lo for kw in kws)
        ]

    df_healthy["_sources"] = df_healthy[target_col].apply(_find_sources)
    exploded = df_healthy["_sources"].explode().dropna()

    counts = exploded.value_counts()
    pct    = (counts / len(df_healthy) * 100).round(1)

    result = pd.DataFrame({
        "Protein Source": counts.index,
        "# Products":     counts.values,
        "% of Healthy Snacks": pct.values,
    })
    return result


@st.cache_data(show_spinner=False)
def get_nova_breakdown(_df: pd.DataFrame) -> pd.DataFrame:
    """
    NOVA processing level breakdown for healthy snacks.
    """
    nova_map = {
        1: "NOVA 1 — Unprocessed whole foods",
        2: "NOVA 2 — Processed culinary ingredients",
        3: "NOVA 3 — Processed foods (acceptable)",
        4: "NOVA 4 — Ultra-processed (⚠️ chemicals)",
    }
    df_healthy = _df[_df["is_healthy"] == True].dropna(subset=["nova_group"]).copy()
    df_healthy["nova_desc"] = df_healthy["nova_group"].map(nova_map)

    counts = df_healthy["nova_desc"].value_counts(normalize=True) * 100
    result = counts.round(1).reset_index()
    result.columns = ["Processing Level", "% of Healthy Snacks"]
    return result.sort_values("Processing Level")
