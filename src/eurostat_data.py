"""Live data pipeline: pull model inputs straight from the Eurostat API.

Two datasets feed the model:

* ``sbs_sc_ovw``    — enterprise counts by size class (SBS, 2021 onwards)
* ``isoc_cicce_use``— share of enterprises buying paid cloud services

Every fetched value is cached to ``data/eurostat_cache.json`` so the model
runs offline and results stay reproducible; ``refresh=True`` re-hits the API
and updates the snapshot. Micro-enterprise adoption is NOT fetched — Eurostat
ICT surveys only cover firms with 10+ employees — so it stays an explicit
assumption in the YAML.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "data" / "eurostat_cache.json"

# NACE aggregate: industry, construction and market services
# (ex. public admin, membership organisations) — the standard SBS business economy.
NACE_AGG = "B-S_X_O_S94"

# SBS size-class codes that make up each model size class.
FIRM_SIZE_CODES = {
    "micro": ["0-9"],
    "small": ["10-19", "20-49"],  # SBS has no direct 10-49 aggregate
    "medium": ["50-249"],
}

# Eurostat ICT survey size classes -> model size classes.
ADOPTION_SIZE_CODES = {"small": "10-49", "medium": "50-249"}


def _fetch_single_value(dataset: str, params: dict) -> float:
    """Query the Eurostat JSON API and return the single observation.

    Each call is filtered down to exactly one cell; anything else means the
    query is wrong, so we fail loudly rather than guess.
    """
    resp = requests.get(f"{API_BASE}/{dataset}", params={"format": "JSON", "lang": "EN", **params}, timeout=30)
    resp.raise_for_status()
    values = resp.json()["value"]
    if len(values) != 1:
        raise ValueError(f"{dataset} query returned {len(values)} observations, expected 1: {params}")
    return float(next(iter(values.values())))


def fetch_firm_counts(year: int = 2023, geo: str = "EU27_2020") -> dict[str, float]:
    """Enterprise counts per model size class from SBS."""
    counts = {}
    for size_class, codes in FIRM_SIZE_CODES.items():
        counts[size_class] = sum(
            _fetch_single_value(
                "sbs_sc_ovw",
                {"indic_sbs": "ENT_NR", "nace_r2": NACE_AGG, "geo": geo, "time": year, "size_emp": code},
            )
            for code in codes
        )
    return counts


def fetch_adoption_rates(year: int = 2025, geo: str = "EU27_2020") -> dict[str, float]:
    """Share of firms buying paid cloud services (proxy for SaaS adoption)."""
    return {
        size_class: _fetch_single_value(
            "isoc_cicce_use",
            {"indic_is": "E_CC", "unit": "PC_ENT", "geo": geo, "time": year, "size_emp": code},
        )
        / 100.0
        for size_class, code in ADOPTION_SIZE_CODES.items()
    }


def get_inputs(refresh: bool = False, cache_path: Path = DEFAULT_CACHE) -> dict:
    """Return model inputs, from the committed cache unless refresh=True.

    The cache makes runs reproducible and offline-safe; a live refresh
    re-queries Eurostat and rewrites the snapshot with a timestamp.
    """
    cache_path = Path(cache_path)
    if not refresh and cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    inputs = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Eurostat API (sbs_sc_ovw 2023, isoc_cicce_use 2025)",
        "firm_counts": fetch_firm_counts(),
        "adoption_rates": fetch_adoption_rates(),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(inputs, fh, indent=2)
    return inputs


def apply_inputs(cfg: dict, inputs: dict) -> dict:
    """Overlay live/cached Eurostat inputs onto the assumptions config.

    Micro adoption and all spend figures deliberately stay as configured —
    they are analyst assumptions, not Eurostat observations.
    """
    import copy

    out = copy.deepcopy(cfg)
    for size_class, count in inputs["firm_counts"].items():
        out["size_classes"][size_class]["firms"] = count
    for size_class, rate in inputs["adoption_rates"].items():
        out["size_classes"][size_class]["adoption_rate"] = rate
    return out
