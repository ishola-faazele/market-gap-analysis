# 🎯 The "Sugar Trap" — Market Gap Analysis

## A. Executive Summary

Using the OpenFoodFacts database (4.4M products, sampled to 2.5M for efficiency), we identified **Chocolate & Confections** as the #1 Blue Ocean opportunity in the healthy snacking market. Over 99% of products in this category fail strict NHS/WHO nutritional thresholds (Protein > 5g, Sugar < 5g per 100g) cross-validated against Nutri-Score A/B grading. Consumer demand is rising — 33.5% of products in this space already carry health marketing badges — yet almost no manufacturer has cracked the formula. Our proprietary **Blue Ocean Disruption Index (BODI)** scored Chocolate & Confections at 57.9, narrowly edging out Cookies & Biscuits (54.4). We recommend the client develop a **Healthy Chocolate-Coated Protein Biscuit** using dairy/whey-based protein sources and a NOVA 3 (Clean Label) formulation to disrupt the current sea of ultra-processed competitors.

---

## B. Project Links

| Deliverable | Link |
|---|---|
| 📓 **Notebook** | [notebooks/analysis.ipynb](notebooks/analysis.ipynb) |
| 📄 **HTML Export** | [reports/analysis.html](reports/analysis.html) |
| 📊 **Dashboard** | [Streamlit Dashboard](https://ishola-amalitech.streamlit.app/) |
| 📽️ **Presentation** | [reports/presentation.pptx](reports/presentation.pptx) |


---

## C. Technical Explanation

### Data Cleaning (Story 1)

1. **Memory-Efficient Ingestion:** The raw dataset is 12GB+. We built a streaming sampler (`notebooks/utils/sampling.py`) that processes the file in 25,000-row chunks, applying column selection and type casting *before* loading into memory. This eliminated OOM crashes entirely.

2. **Column Pruning:** Dropped columns with > 80% missing data, zero variance, or unit duplicates (e.g., kilojoules vs. kcal). Reduced from 200+ columns to ~40 analytically relevant ones.

3. **Type Casting:** Applied modern Pandas nullable types (`Int64`, `Float64`, `string`, `category`) to reduce memory footprint by ~60% and avoid silent `NaN` coercion bugs.

4. **Outlier Removal:** Filtered biologically impossible values (e.g., sugar > 100g per 100g, negative protein). Rows missing both `sugars_100g` and `proteins_100g` were dropped entirely — we do not impute nutritional data.

5. **Missing Data Policy:** "Drop, don't impute." Fabricating nutritional values in a health-oriented analysis would compromise the integrity of every downstream recommendation.

### Category Wrangling (Story 2)

The raw `categories_tags` field contains 35,000+ unique comma-separated tags in multiple languages (e.g., `fr:biscuits-aux-pepites-de-chocolat`). We built a two-tier classification system:

1. **Taxonomy Filter:** Used `categories_tags` to identify true snack products via the `en:snacks` hierarchy tag.
2. **Multi-Lingual Heuristic Map:** A keyword-based mapper applied to `main_category_en` that groups products into **9 Actionable Categories** (Chocolate & Confections, Cookies & Biscuits, Chips & Crisps, Pastries/Cakes, Nuts/Seeds, Cereal Bars, Protein Bars, Fruit Snacks, Crackers). The "Other Snacks" residual bucket was iteratively reduced from 41% to ~15% through successive keyword refinement.

### Health Validation (Story 3 & 4)

We rejected arbitrary median-split thresholds in favor of a **dual-signal validation framework:**

- **NHS/WHO Standards:** Protein > 5g/100g AND Sugar < 5g/100g.
- **Nutri-Score Guardrail:** Product must also achieve a Nutri-Score of A or B. This prevents recommending products that hit macros but are loaded with saturated fat, sodium, or additives ("health-washing").

### The Blue Ocean Disruption Index — BODI (Story 4)

To move beyond subjective chart-reading, we developed a composite metric:

```
BODI = √(Normalized_Supply_Gap × Normalized_Demand)
```

- **Supply Gap:** % of products in each category that fail the health test, weighted by √(market size) to penalize tiny categories.
- **Demand:** % of products carrying health marketing labels (e.g., "High Protein", "Vegan", "No Added Sugar"), normalized to a 0–100 scale.
- **Geometric Mean:** Ensures a category only scores high if BOTH supply gap and demand are simultaneously large. A massive gap with zero demand scores zero — preventing dead-end recommendations.

### Candidate's Choice — The "Clean Label" Vulnerability Index (Story 6)

**What we added:** A NOVA-based processing analysis of the products that *pass* the health check.

**Why:** Hitting macro-nutrient targets was the health trend of the 2010s. The consumer trend of the 2020s is **Clean Label** — minimally processed, recognizable ingredients, no chemicals. Using the NOVA Classification System (1 = Unprocessed → 4 = Ultra-Processed), we discovered that the vast majority of "healthy" snacks achieving good macros are classified as **NOVA 4 (Ultra-Processed)** — meaning they rely on protein isolates, emulsifiers, and artificial sweeteners.

**The strategic value:** This gives our client a second axis of disruption. Instead of just matching the macros, they should formulate a **NOVA 3** (processed but not ultra-processed) recipe using real, recognizable ingredients. This captures the growing premium "Clean Label" segment that no competitor currently occupies.

---

## Project Structure

```
mga/
├── dashboard/
│   ├── app.py                      # Streamlit dashboard (main entry point)
│   └── utils/
│       ├── __init__.py
│       └── data_loader.py          # Data loading, analysis, and caching engine
├── notebooks/
│   ├── analysis.ipynb              # Full analysis notebook
│   └── utils/
│       ├── __init__.py
│       └── sampling.py             # Memory-efficient streaming sampler
├── reports/
│   └── analysis.html               # HTML export of the notebook
├── data/
│   └── openfoodfacts_clean.csv.gz  # Compressed clean dataset (committed)
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## How to Run Locally

```bash
# 1. Clone the repo
git clone https://github.com/ishola-faazele/market-gap-analysis.git
cd market-gap-analysis

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the dashboard
streamlit run dashboard/app.py
```

The dashboard will open at `http://localhost:8501`.

---

## Tech Stack

| Tool | Purpose |
|---|---|
| Python 3.13 | Core language |
| Pandas / NumPy | Data wrangling & analysis |
| Plotly | Interactive visualizations |
| Matplotlib | Static notebook charts |
| Streamlit | Interactive dashboard |
| Jupyter Notebook | Analysis & presentation |
| OpenFoodFacts | Data source (4.4M products) |
