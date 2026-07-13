"""Monte Carlo simulation over the market-sizing funnel.

Instead of single point estimates, each uncertain driver gets a probability
distribution matched to its evidence quality (see config/assumptions.yaml):

* adoption rates      — truncated normal around the Eurostat observation
* SaaS spend per firm — lognormal (spend data is right-skewed; benchmarks
                        skew toward US/UK samples)
* region / wallet / peak share — triangular around the analyst assumption

10,000 draws propagate through TAM -> SAM -> SOM, giving percentile bands
(P10/P50/P90) on obtainable revenue rather than a single number — the
difference between "SOM is €11m" and "SOM is €6-19m with 80% confidence".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .sizing import _logistic_ramp


def _draw(rng: np.random.Generator, base: float, spec: dict, n: int) -> np.ndarray:
    """Sample n values for a driver around its base-case value."""
    kind = spec["dist"]
    if kind == "truncnorm":
        draws = rng.normal(base, base * spec["rel_sd"], n)
        return np.clip(draws, 0.0, 1.0)  # adoption rates are shares
    if kind == "lognormal":
        sigma = spec["sigma"]
        # median of lognormal = exp(mu) -> anchor the median at the base case
        return rng.lognormal(np.log(base), sigma, n)
    if kind == "triangular":
        return rng.triangular(base * spec["rel_low"], base, base * spec["rel_high"], n)
    raise ValueError(f"Unknown distribution: {kind}")


def run_simulation(cfg: dict) -> dict:
    """Vectorised Monte Carlo over the SAM/SOM funnel.

    Returns the year-5 SOM distribution, a per-year percentile fan for the
    base scenario, and summary statistics.
    """
    mc = cfg["monte_carlo"]
    rng = np.random.default_rng(mc["seed"])
    n = mc["n_sims"]
    dists = mc["distributions"]

    # --- ICP spend pool: small + medium firms (micro excluded from SAM) ----
    icp = {k: v for k, v in cfg["size_classes"].items() if k not in cfg["sam"]["exclude_size_classes"]}
    icp_tam = np.zeros(n)
    for sc in icp.values():
        adoption = _draw(rng, sc["adoption_rate"], dists["adoption_rate"], n)
        spend = _draw(rng, sc["annual_saas_spend_eur"], dists["annual_saas_spend_eur"], n)
        icp_tam += sc["firms"] * adoption * spend

    # --- SAM filters --------------------------------------------------------
    region = _draw(rng, cfg["sam"]["target_region_share"], dists["target_region_share"], n)
    wallet = _draw(rng, cfg["sam"]["category_wallet_share"], dists["category_wallet_share"], n)
    sam = icp_tam * np.clip(region, 0, 1) * np.clip(wallet, 0, 1)

    # --- SOM: base-scenario S-curve ramp with uncertain peak share ---------
    base_scen = cfg["som"]["scenarios"]["base"]
    peak = _draw(rng, base_scen["peak_share"], dists["peak_share"], n)
    horizon = cfg["som"]["horizon_years"]
    years = np.arange(1, horizon + 1, dtype=float)
    ramp = _logistic_ramp(years, base_scen["ramp_midpoint_year"], base_scen["ramp_steepness"])

    som_paths = sam[:, None] * peak[:, None] * ramp[None, :]  # (n_sims, years)

    fan = pd.DataFrame(
        {
            "year": years.astype(int),
            "p10": np.percentile(som_paths, 10, axis=0),
            "p50": np.percentile(som_paths, 50, axis=0),
            "p90": np.percentile(som_paths, 90, axis=0),
        }
    )
    som_y5 = som_paths[:, -1]
    return {
        "som_y5_draws": som_y5,
        "fan": fan,
        "summary": {
            "p10": float(np.percentile(som_y5, 10)),
            "p50": float(np.percentile(som_y5, 50)),
            "p90": float(np.percentile(som_y5, 90)),
            "mean": float(som_y5.mean()),
        },
    }


def prob_exceeds(draws: np.ndarray, threshold_eur: float) -> float:
    """P(year-5 SOM > threshold) — the number a go/no-go decision hangs on."""
    return float((draws > threshold_eur).mean())
