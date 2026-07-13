"""CLI entry point: run the full sizing model + Monte Carlo, print a summary
and save figures + result CSVs to outputs/.

Usage:
    python run_analysis.py             # Eurostat inputs from committed cache
    python run_analysis.py --refresh   # re-fetch live from the Eurostat API
    python run_analysis.py --offline   # static YAML fallback values only
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.assumptions import load_assumptions
from src.charts import (
    funnel_chart,
    mc_fan_chart,
    mc_histogram_chart,
    som_ramp_chart,
    tam_composition_chart,
    tornado_chart,
)
from src.eurostat_data import apply_inputs, get_inputs
from src.monte_carlo import prob_exceeds, run_simulation
from src.sensitivity import tornado
from src.sizing import run_model

OUT_DIR = Path(__file__).resolve().parent / "outputs"
FIG_DIR = OUT_DIR / "figures"


def main() -> None:
    parser = argparse.ArgumentParser(description="EU-27 SME SaaS market sizing")
    parser.add_argument("--refresh", action="store_true", help="re-fetch inputs from the Eurostat API")
    parser.add_argument("--offline", action="store_true", help="skip the data pipeline, use YAML fallbacks")
    args = parser.parse_args()

    cfg = load_assumptions()
    data_note = "static YAML fallbacks"
    if not args.offline:
        inputs = get_inputs(refresh=args.refresh)
        cfg = apply_inputs(cfg, inputs)
        data_note = f"{inputs['source']} — cached {inputs['fetched_at']}"

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    results = run_model(cfg)
    tor = tornado(cfg)
    mc = run_simulation(cfg)

    tam = results["tam_eur"]
    sam = results["sam"]["sam_eur"]
    horizon = cfg["som"]["horizon_years"]
    som = results["som"]
    som_y5 = float(som[(som["scenario"] == "base") & (som["year"] == horizon)]["som_eur"].iloc[0])

    # ---- console summary ---------------------------------------------------
    gap = (tam - results["top_down_tam_eur"]) / results["top_down_tam_eur"]
    s = mc["summary"]
    print("=" * 68)
    print("EU-27 SME SaaS market sizing — summary")
    print(f"Data: {data_note}")
    print("=" * 68)
    print(f"Bottom-up TAM:          €{tam / 1e9:6.1f} bn / year")
    print(f"Top-down cross-check:   €{results['top_down_tam_eur'] / 1e9:6.1f} bn / year  (gap {gap:+.1%})")
    print(f"SAM:                    €{sam / 1e9:6.2f} bn / year")
    print(f"SOM (deterministic y{horizon}): €{som_y5 / 1e6:6.1f} m / year")
    print(f"SOM (Monte Carlo y{horizon}):   P10 €{s['p10'] / 1e6:.1f}m · P50 €{s['p50'] / 1e6:.1f}m · P90 €{s['p90'] / 1e6:.1f}m")
    print(f"P(SOM y{horizon} > €10m):       {prob_exceeds(mc['som_y5_draws'], 10e6):.0%}")
    print("-" * 68)
    print(results["tam_by_size_class"].to_string(index=False))

    # ---- artifacts -----------------------------------------------------------
    results["tam_by_size_class"].to_csv(OUT_DIR / "tam_by_size_class.csv", index=False)
    som.to_csv(OUT_DIR / "som_scenarios.csv", index=False)
    tor.to_csv(OUT_DIR / "sensitivity.csv", index=False)
    mc["fan"].to_csv(OUT_DIR / "mc_fan.csv", index=False)

    funnel_chart(tam, sam, som_y5, FIG_DIR / "01_funnel.png")
    tam_composition_chart(results["tam_by_size_class"], FIG_DIR / "02_tam_by_size_class.png")
    som_ramp_chart(som, FIG_DIR / "03_som_ramp.png")
    tornado_chart(tor, FIG_DIR / "04_tornado.png")
    mc_histogram_chart(mc["som_y5_draws"], s, FIG_DIR / "05_mc_distribution.png")
    mc_fan_chart(mc["fan"], FIG_DIR / "06_mc_fan.png")
    print(f"\nFigures and CSVs written to {OUT_DIR}")


if __name__ == "__main__":
    main()
