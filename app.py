"""Streamlit app — interactive TAM/SAM/SOM model for EU-27 SME SaaS.

Run with:  streamlit run app.py
Sidebar sliders flex the key assumptions live; every figure and metric
recomputes from the same engine used by the CLI (src/sizing.py).
"""

import copy

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.assumptions import load_assumptions
from src.eurostat_data import apply_inputs, get_inputs
from src.monte_carlo import prob_exceeds, run_simulation
from src.sensitivity import tornado
from src.sizing import run_model

st.set_page_config(page_title="EU SME SaaS Market Sizing", layout="wide")


@st.cache_data
def base_config() -> dict:
    """Assumptions overlaid with Eurostat inputs (cached snapshot)."""
    cfg = load_assumptions()
    try:
        inputs = get_inputs()  # committed cache; refresh happens via CLI
        cfg = apply_inputs(cfg, inputs)
        cfg["_data_note"] = f"{inputs['source']} · snapshot {inputs['fetched_at'][:10]}"
    except Exception:
        cfg["_data_note"] = "static YAML fallbacks (pipeline unavailable)"
    return cfg


def eur(x: float) -> str:
    return f"€{x / 1e9:.1f}bn" if x >= 1e9 else f"€{x / 1e6:.1f}m"


# ---------------- sidebar: assumption overrides ----------------
cfg = copy.deepcopy(base_config())
st.sidebar.header("Assumptions")
st.sidebar.caption(f"Data: {cfg.pop('_data_note', 'n/a')}. Spend levels are analyst assumptions — see README.")

with st.sidebar.expander("Adoption rates", expanded=True):
    for name, sc in cfg["size_classes"].items():
        sc["adoption_rate"] = st.slider(
            f"{name} (paid SaaS adoption)", 0.0, 1.0, float(sc["adoption_rate"]), 0.01
        )

with st.sidebar.expander("Annual SaaS spend per adopting firm (€)"):
    for name, sc in cfg["size_classes"].items():
        sc["annual_saas_spend_eur"] = st.number_input(
            f"{name}", min_value=100, value=int(sc["annual_saas_spend_eur"]), step=500
        )

with st.sidebar.expander("SAM filters"):
    cfg["sam"]["target_region_share"] = st.slider(
        "Target region share of EU SME base", 0.05, 1.0, float(cfg["sam"]["target_region_share"]), 0.01
    )
    cfg["sam"]["category_wallet_share"] = st.slider(
        "Product category share of SaaS wallet", 0.01, 1.0, float(cfg["sam"]["category_wallet_share"]), 0.01
    )

with st.sidebar.expander("SOM scenarios (peak share of SAM)"):
    for name, sc in cfg["som"]["scenarios"].items():
        sc["peak_share"] = st.slider(f"{name}", 0.001, 0.10, float(sc["peak_share"]), 0.001, format="%.3f")

# ---------------- model run ----------------
results = run_model(cfg)
tam, sam = results["tam_eur"], results["sam"]["sam_eur"]
horizon = cfg["som"]["horizon_years"]
som = results["som"]
som_y5 = float(som[(som["scenario"] == "base") & (som["year"] == horizon)]["som_eur"].iloc[0])

st.title("EU-27 SME SaaS — TAM / SAM / SOM model")
st.caption(
    "Bottom-up market sizing for a hypothetical productivity SaaS targeting European SMEs, "
    "cross-validated top-down. Built with the same structure as a consulting Excel model — "
    "assumptions, engine, and outputs fully separated."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("TAM (bottom-up)", eur(tam))
gap = (tam - results["top_down_tam_eur"]) / results["top_down_tam_eur"]
c2.metric("Top-down cross-check", eur(results["top_down_tam_eur"]), f"{gap:+.0%} vs bottom-up")
c3.metric("SAM", eur(sam))
c4.metric(f"SOM (base, yr {horizon})", eur(som_y5))

left, right = st.columns(2)

with left:
    st.subheader("TAM by size class")
    fig = px.bar(
        results["tam_by_size_class"], x="size_class", y="tam_eur",
        labels={"tam_eur": "TAM (€/yr)", "size_class": ""},
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("SOM ramp by scenario")
    fig = px.line(
        som, x="year", y="som_eur", color="scenario", markers=True,
        labels={"som_eur": "SOM (€/yr)"},
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Sensitivity — year-5 base-case SOM (drivers flexed by uncertainty range)")
tor = tornado(cfg)
fig = go.Figure()
fig.add_trace(
    go.Bar(
        y=tor["driver"], orientation="h",
        base=tor["low_eur"], x=tor["high_eur"] - tor["low_eur"],
        marker_color="#2e6f9e",
    )
)
fig.add_vline(x=float(tor["base_eur"].iloc[0]), line_dash="dash")
fig.update_layout(xaxis_title="Year-5 SOM (€/yr)", yaxis=dict(autorange="reversed"))
st.plotly_chart(fig, use_container_width=True)

st.subheader("Monte Carlo — year-5 SOM under uncertainty (10,000 draws)")
mc = run_simulation(cfg)
s = mc["summary"]
m1, m2, m3, m4 = st.columns(4)
m1.metric("P10 (conservative)", eur(s["p10"]))
m2.metric("P50 (median)", eur(s["p50"]))
m3.metric("P90 (upside)", eur(s["p90"]))
threshold = st.slider("Viability threshold (€m/yr)", 1, 50, 10)
m4.metric(f"P(SOM > €{threshold}m)", f"{prob_exceeds(mc['som_y5_draws'], threshold * 1e6):.0%}")

mc_left, mc_right = st.columns(2)
with mc_left:
    fig = px.histogram(x=mc["som_y5_draws"] / 1e6, nbins=80,
                       labels={"x": "Year-5 SOM (€m)"}, title="Distribution of outcomes")
    st.plotly_chart(fig, use_container_width=True)
with mc_right:
    fan = mc["fan"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fan["year"], y=fan["p90"] / 1e6, line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=fan["year"], y=fan["p10"] / 1e6, fill="tonexty",
                             name="P10–P90", line=dict(width=0)))
    fig.add_trace(go.Scatter(x=fan["year"], y=fan["p50"] / 1e6, name="Median", mode="lines+markers"))
    fig.update_layout(title="SOM ramp with uncertainty band", xaxis_title="Year", yaxis_title="SOM (€m/yr)")
    st.plotly_chart(fig, use_container_width=True)

with st.expander("Methodology and sources"):
    st.markdown(
        """
- **TAM (bottom-up):** firms × paid-SaaS adoption × annual spend, per size class.
  Firm counts: Eurostat (2024). Adoption (small 49.3%, medium 66.8%): Eurostat
  *Cloud computing services by size class* (2025). Micro adoption and spend levels
  are documented analyst assumptions.
- **Cross-check (top-down):** European SaaS market (~$92.7bn, 2025) × assumed SME share.
- **SAM:** ICP = 10–249 employees, DACH+Benelux+Nordics, productivity-category wallet share.
- **SOM:** logistic share ramp to a scenario-specific peak share of SAM over 5 years.
        """
    )
