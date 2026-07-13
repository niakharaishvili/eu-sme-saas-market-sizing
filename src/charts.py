"""Static matplotlib figures for the CLI run (saved to outputs/figures)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe
import matplotlib.pyplot as plt
import pandas as pd

COLORS = {"tam": "#1f3b5c", "sam": "#2e6f9e", "som": "#7fb3d5"}


def _eur_bn(x: float) -> str:
    return f"€{x / 1e9:.1f}bn" if x >= 1e9 else f"€{x / 1e6:.0f}m"


def funnel_chart(tam: float, sam: float, som_y5: float, path: Path) -> None:
    """TAM -> SAM -> SOM funnel as a horizontal bar chart (log-friendly)."""
    labels = ["TAM\n(EU-27 SME SaaS)", "SAM\n(ICP x region x category)", "SOM\n(base case, year 5)"]
    values = [tam, sam, som_y5]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.barh(labels[::-1], values[::-1], color=[COLORS["som"], COLORS["sam"], COLORS["tam"]])
    for bar, v in zip(bars, values[::-1]):
        ax.text(bar.get_width() * 1.02, bar.get_y() + bar.get_height() / 2, _eur_bn(v), va="center")
    ax.set_xscale("log")
    ax.set_xlabel("EUR per year (log scale)")
    ax.set_title("EU-27 SME SaaS — market sizing funnel")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def tam_composition_chart(tam_df: pd.DataFrame, path: Path) -> None:
    """TAM split by size class — shows where the money actually sits."""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(tam_df["size_class"], tam_df["tam_eur"] / 1e9, color=COLORS["sam"])
    for i, v in enumerate(tam_df["tam_eur"] / 1e9):
        ax.text(i, v + 0.2, f"€{v:.1f}bn", ha="center")
    ax.set_ylabel("TAM (EUR bn / year)")
    ax.set_title("Bottom-up TAM by enterprise size class")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def som_ramp_chart(som_df: pd.DataFrame, path: Path) -> None:
    """Obtainable revenue ramp per scenario."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for scenario, grp in som_df.groupby("scenario"):
        ax.plot(grp["year"], grp["som_eur"] / 1e6, marker="o", label=scenario)
    ax.set_xlabel("Year")
    ax.set_ylabel("SOM (EUR m / year)")
    ax.set_title("Obtainable market (SOM) ramp by scenario")
    ax.legend(title="Scenario")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def mc_histogram_chart(draws, summary: dict, path: Path) -> None:
    """Distribution of year-5 SOM across 10k simulations."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(draws / 1e6, bins=80, color=COLORS["sam"], alpha=0.85)
    for pct, style in (("p10", ":"), ("p50", "--"), ("p90", ":")):
        ax.axvline(summary[pct] / 1e6, color="black", linestyle=style, linewidth=1,
                   label=f"{pct.upper()}: €{summary[pct] / 1e6:.1f}m")
    ax.set_xlabel("Year-5 SOM (EUR m)")
    ax.set_ylabel("Simulations")
    ax.set_title("Monte Carlo — year-5 SOM distribution (10,000 draws)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def mc_fan_chart(fan: pd.DataFrame, path: Path) -> None:
    """P10-P90 band around the median SOM ramp."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.fill_between(fan["year"], fan["p10"] / 1e6, fan["p90"] / 1e6,
                    color=COLORS["som"], alpha=0.5, label="P10–P90 band")
    ax.plot(fan["year"], fan["p50"] / 1e6, color=COLORS["tam"], marker="o", label="Median (P50)")
    ax.set_xlabel("Year")
    ax.set_ylabel("SOM (EUR m / year)")
    ax.set_title("Monte Carlo — obtainable market ramp with uncertainty band")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def tornado_chart(tor_df: pd.DataFrame, path: Path) -> None:
    """One-way sensitivity of year-5 base-case SOM."""
    fig, ax = plt.subplots(figsize=(9, 4.5))
    base = tor_df["base_eur"].iloc[0] / 1e6
    y = range(len(tor_df))[::-1]
    ax.barh(
        list(y),
        (tor_df["high_eur"] - tor_df["low_eur"]) / 1e6,
        left=tor_df["low_eur"] / 1e6,
        color=COLORS["sam"],
    )
    ax.axvline(base, color="black", linewidth=1, linestyle="--", label=f"Base: €{base:.1f}m")
    ax.set_yticks(list(y))
    ax.set_yticklabels(tor_df["driver"])
    ax.set_xlabel("Year-5 SOM (EUR m)")
    ax.set_title("Sensitivity of year-5 SOM (drivers flexed by uncertainty range)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
