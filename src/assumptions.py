"""Load and validate model assumptions from config/assumptions.yaml.

Keeping every input in one YAML file mirrors how a consulting model keeps
its assumptions tab separate from calculation tabs: anyone can audit or
flex an input without touching the logic.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "assumptions.yaml"


def load_assumptions(path: str | Path = DEFAULT_PATH) -> dict:
    """Read the YAML assumptions file and run basic validation."""
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    _validate(cfg)
    return cfg


def _validate(cfg: dict) -> None:
    """Fail fast on inputs that would silently produce nonsense."""
    for name, sc in cfg["size_classes"].items():
        if sc["firms"] <= 0:
            raise ValueError(f"{name}: firm count must be positive")
        if not 0 <= sc["adoption_rate"] <= 1:
            raise ValueError(f"{name}: adoption_rate must be in [0, 1]")
        if sc["annual_saas_spend_eur"] <= 0:
            raise ValueError(f"{name}: annual spend must be positive")

    sam = cfg["sam"]
    for key in ("target_region_share", "category_wallet_share"):
        if not 0 < sam[key] <= 1:
            raise ValueError(f"sam.{key} must be in (0, 1]")

    unknown = set(sam["exclude_size_classes"]) - set(cfg["size_classes"])
    if unknown:
        raise ValueError(f"sam.exclude_size_classes references unknown classes: {unknown}")

    for name, sc in cfg["som"]["scenarios"].items():
        if not 0 < sc["peak_share"] < 1:
            raise ValueError(f"scenario {name}: peak_share must be in (0, 1)")
