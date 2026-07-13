"""Sanity tests: the funnel must narrow, and inputs must move outputs
in the expected direction."""

import copy

import pytest

from src.assumptions import load_assumptions
from src.sensitivity import tornado
from src.sizing import run_model


@pytest.fixture(scope="module")
def cfg():
    return load_assumptions()


def test_funnel_narrows(cfg):
    r = run_model(cfg)
    horizon = cfg["som"]["horizon_years"]
    som = r["som"]
    y5 = som[(som["scenario"] == "base") & (som["year"] == horizon)]["som_eur"].iloc[0]
    assert r["tam_eur"] > r["sam"]["sam_eur"] > y5 > 0


def test_bottom_up_within_50pct_of_top_down(cfg):
    """Triangulation guard: bottom-up and top-down TAM should be same order."""
    r = run_model(cfg)
    gap = abs(r["tam_eur"] - r["top_down_tam_eur"]) / r["top_down_tam_eur"]
    assert gap < 0.5


def test_higher_adoption_raises_tam(cfg):
    bumped = copy.deepcopy(cfg)
    for sc in bumped["size_classes"].values():
        sc["adoption_rate"] = min(sc["adoption_rate"] * 1.1, 1.0)
    assert run_model(bumped)["tam_eur"] > run_model(cfg)["tam_eur"]


def test_scenarios_are_ordered(cfg):
    som = run_model(cfg)["som"]
    horizon = cfg["som"]["horizon_years"]
    y5 = som[som["year"] == horizon].set_index("scenario")["som_eur"]
    assert y5["conservative"] < y5["base"] < y5["aggressive"]


def test_tornado_bounds_bracket_base(cfg):
    tor = tornado(cfg)
    assert ((tor["low_eur"] <= tor["base_eur"]) & (tor["base_eur"] <= tor["high_eur"])).all()


def test_cached_eurostat_inputs_apply(cfg):
    """The committed cache must load and overwrite firm counts/adoption."""
    from src.eurostat_data import apply_inputs, get_inputs

    inputs = get_inputs(refresh=False)  # no network: reads data/eurostat_cache.json
    merged = apply_inputs(cfg, inputs)
    assert merged["size_classes"]["small"]["firms"] == inputs["firm_counts"]["small"]
    assert 0 < merged["size_classes"]["medium"]["adoption_rate"] < 1
    # micro adoption stays an assumption — pipeline must not touch it
    assert merged["size_classes"]["micro"]["adoption_rate"] == cfg["size_classes"]["micro"]["adoption_rate"]


def test_monte_carlo_percentiles_ordered_and_reproducible(cfg):
    from src.monte_carlo import run_simulation

    a = run_simulation(cfg)["summary"]
    b = run_simulation(cfg)["summary"]
    assert a == b  # fixed seed -> identical results
    assert a["p10"] < a["p50"] < a["p90"]


def test_monte_carlo_median_near_deterministic(cfg):
    """The MC median should sit near the deterministic base case, not drift."""
    from src.monte_carlo import run_simulation

    det = run_model(cfg)
    horizon = cfg["som"]["horizon_years"]
    som = det["som"]
    det_y5 = float(som[(som["scenario"] == "base") & (som["year"] == horizon)]["som_eur"].iloc[0])
    mc_p50 = run_simulation(cfg)["summary"]["p50"]
    assert abs(mc_p50 - det_y5) / det_y5 < 0.35


def test_invalid_adoption_rejected(cfg):
    bad = copy.deepcopy(cfg)
    bad["size_classes"]["small"]["adoption_rate"] = 1.5
    from src.assumptions import _validate

    with pytest.raises(ValueError):
        _validate(bad)
