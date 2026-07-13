"""One-way sensitivity analysis (tornado chart data).

Each driver is flexed +/- its own uncertainty range (defined in
config/assumptions.yaml) while everything else is held at base case, and
the impact on year-5 base-scenario SOM is recorded. This is the coded
equivalent of an Excel one-way data table, with ranges scaled to how
well-evidenced each input is.
"""

from __future__ import annotations

import copy

import pandas as pd

from .sizing import run_model


def _year5_base_som(cfg: dict) -> float:
    som = run_model(cfg)["som"]
    horizon = cfg["som"]["horizon_years"]
    row = som[(som["scenario"] == "base") & (som["year"] == horizon)]
    return float(row["som_eur"].iloc[0])


def _flex(cfg: dict, driver: str, factor: float) -> dict:
    """Return a deep-copied config with one driver scaled by `factor`."""
    out = copy.deepcopy(cfg)
    if driver in ("adoption_rate", "annual_saas_spend_eur"):
        for sc in out["size_classes"].values():
            sc[driver] = min(sc[driver] * factor, 1.0) if driver == "adoption_rate" else sc[driver] * factor
    elif driver in ("target_region_share", "category_wallet_share"):
        out["sam"][driver] = min(out["sam"][driver] * factor, 1.0)
    elif driver == "peak_share":
        out["som"]["scenarios"]["base"]["peak_share"] *= factor
    else:
        raise ValueError(f"Unknown sensitivity driver: {driver}")
    return out


def tornado(cfg: dict) -> pd.DataFrame:
    """Low/high year-5 SOM for each driver, sorted by impact (widest first)."""
    base = _year5_base_som(cfg)
    rows = []
    for driver, flex in cfg["sensitivity"]["drivers"].items():
        low = _year5_base_som(_flex(cfg, driver, 1 - flex))
        high = _year5_base_som(_flex(cfg, driver, 1 + flex))
        rows.append(
            {
                "driver": f"{driver} (±{flex:.0%})",
                "base_eur": base,
                "low_eur": low,
                "high_eur": high,
                "swing_eur": abs(high - low),
            }
        )
    return pd.DataFrame(rows).sort_values("swing_eur", ascending=False).reset_index(drop=True)
