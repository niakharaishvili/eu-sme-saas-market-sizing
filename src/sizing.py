"""TAM / SAM / SOM engine.

Methodology (bottom-up):
    TAM  = sum over size classes of  firms x adoption_rate x annual SaaS spend
    SAM  = TAM restricted to the ICP size classes, then filtered by
           target-region share and product-category wallet share
    SOM  = SAM x obtainable market share, ramped over the horizon with a
           logistic (S-curve) per scenario

A top-down cross-check (Europe SaaS market x assumed SME share) validates
the bottom-up TAM — the classic consulting triangulation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def tam_by_size_class(cfg: dict) -> pd.DataFrame:
    """Bottom-up TAM: one row per size class, EUR per year."""
    rows = []
    for name, sc in cfg["size_classes"].items():
        adopters = sc["firms"] * sc["adoption_rate"]
        rows.append(
            {
                "size_class": name,
                "firms": sc["firms"],
                "adoption_rate": sc["adoption_rate"],
                "adopting_firms": adopters,
                "annual_saas_spend_eur": sc["annual_saas_spend_eur"],
                "tam_eur": adopters * sc["annual_saas_spend_eur"],
            }
        )
    return pd.DataFrame(rows)


def top_down_tam_eur(cfg: dict) -> float:
    """Top-down cross-check: Europe SaaS market x assumed SME share, in EUR."""
    m = cfg["market"]
    return m["europe_saas_market_usd_bn"] * 1e9 * m["usd_to_eur"] * m["sme_share_of_saas_spend"]


def compute_sam(cfg: dict, tam_df: pd.DataFrame) -> dict:
    """Apply ICP, region and category filters to the relevant TAM slice."""
    sam_cfg = cfg["sam"]
    icp = tam_df[~tam_df["size_class"].isin(sam_cfg["exclude_size_classes"])]
    icp_tam = icp["tam_eur"].sum()
    sam = icp_tam * sam_cfg["target_region_share"] * sam_cfg["category_wallet_share"]
    return {
        "icp_tam_eur": icp_tam,
        "target_region_share": sam_cfg["target_region_share"],
        "category_wallet_share": sam_cfg["category_wallet_share"],
        "sam_eur": sam,
    }


def _logistic_ramp(years: np.ndarray, midpoint: float, steepness: float) -> np.ndarray:
    """S-curve in [0, 1]: slow start, acceleration, plateau at peak share."""
    return 1.0 / (1.0 + np.exp(-steepness * (years - midpoint)))


def compute_som(cfg: dict, sam_eur: float) -> pd.DataFrame:
    """Yearly obtainable revenue per scenario over the planning horizon."""
    horizon = cfg["som"]["horizon_years"]
    years = np.arange(1, horizon + 1, dtype=float)
    rows = []
    for name, sc in cfg["som"]["scenarios"].items():
        share = sc["peak_share"] * _logistic_ramp(
            years, sc["ramp_midpoint_year"], sc["ramp_steepness"]
        )
        for yr, s in zip(years, share):
            rows.append(
                {
                    "scenario": name,
                    "year": int(yr),
                    "market_share": s,
                    "som_eur": sam_eur * s,
                }
            )
    return pd.DataFrame(rows)


def run_model(cfg: dict) -> dict:
    """Run the full funnel and return every intermediate for inspection."""
    tam_df = tam_by_size_class(cfg)
    tam = tam_df["tam_eur"].sum()
    sam = compute_sam(cfg, tam_df)
    som_df = compute_som(cfg, sam["sam_eur"])
    return {
        "tam_by_size_class": tam_df,
        "tam_eur": tam,
        "top_down_tam_eur": top_down_tam_eur(cfg),
        "sam": sam,
        "som": som_df,
    }
