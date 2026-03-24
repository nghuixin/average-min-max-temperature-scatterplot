from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_MIN_YEAR = 2000
SCATTER_PLOT_MAX_POINTS = 50_000
CHUNK_ROWS = 400_000
# Minimum daily observations per element (TMIN / TMAX) for top plot_status tier.
MIN_OBS_FOR_VALID_SCATTER = 6

# Source files may use alternate labels; logic and outputs use canonical names.
WEEK_STATUS_CANONICAL = {
    "valid_week": "valid_data",
}


def canonicalize_week_status(series: pd.Series) -> pd.Series:
    """Map aliases to canonical week_status (e.g. ``valid_week`` -> ``valid_data``)."""
    out = series.copy()
    mask = out.notna()
    if not mask.any():
        return out
    out.loc[mask] = out.loc[mask].astype(str).str.strip().replace(WEEK_STATUS_CANONICAL)
    return out


EXPECTED_COLUMNS = {
    "station_id",
    "year",
    "week_of_year",
    "element",
    "n_obs",
    "weekly_mean",
    "week_status",
}


def load_weekly_data(path: Path) -> pd.DataFrame:
    """Load CSV and validate the expected weekly schema."""
    df = pd.read_csv(path)
    missing = EXPECTED_COLUMNS.difference(df.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Missing expected columns: {missing_text}")
    return df


def load_japan_weekly_tmin_tmax(
    path: Path,
    min_year: int = DEFAULT_MIN_YEAR,
    chunksize: int = CHUNK_ROWS,
) -> pd.DataFrame:
    """
    Load long-format rows for TMIN/TMAX only, year >= min_year, via chunked reads.
    Reduces memory versus loading the full multi-element file at once.
    """
    usecols = list(EXPECTED_COLUMNS)
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=chunksize):
        chunk = chunk[chunk["element"].isin(["TMIN", "TMAX"])]
        chunk = chunk[chunk["year"] >= min_year]
        if not chunk.empty:
            chunks.append(chunk)
    if not chunks:
        return pd.DataFrame(columns=sorted(EXPECTED_COLUMNS))
    return pd.concat(chunks, ignore_index=True)


def load_station_names(path: Path) -> pd.DataFrame:
    """Load station_id -> station_name from the stations lookup CSV."""
    df = pd.read_csv(path, usecols=["station_id", "name"])
    df = df.rename(columns={"name": "station_name"})
    df["station_name"] = df["station_name"].astype(str).str.strip()
    return df


def merge_station_names(scatter_df: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    out = scatter_df.merge(stations, on="station_id", how="left")
    if "station_name" in out.columns:
        out["station_name"] = out["station_name"].fillna("")
    return out


SEASON_WINTER = "Winter"
SEASON_SPRING = "Spring"
SEASON_SUMMER = "Summer"
SEASON_AUTUMN = "Autumn"

# Week-of-year bands: Winter 1–9 and 49–52; Spring 10–22; Summer 23–35; Autumn 36–48.
# Week 53 (if present) is grouped with Winter (late year).
ALL_SEASONS: tuple[str, ...] = (
    SEASON_WINTER,
    SEASON_SPRING,
    SEASON_SUMMER,
    SEASON_AUTUMN,
)


def assign_season_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``season`` from ``week_of_year`` using project week-band definitions."""
    out = df.copy()
    w = pd.to_numeric(out["week_of_year"], errors="coerce")
    conditions = [
        ((w >= 1) & (w <= 9)) | ((w >= 49) & (w <= 53)),
        (w >= 10) & (w <= 22),
        (w >= 23) & (w <= 35),
        (w >= 36) & (w <= 48),
    ]
    choices = [SEASON_WINTER, SEASON_SPRING, SEASON_SUMMER, SEASON_AUTUMN]
    out["season"] = np.select(conditions, choices, default="Unknown")
    return out


def sort_scatter_plot_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Alphabetical order: station_name (if present), then station_id, week_of_year, year."""
    if df.empty:
        return df.copy()
    keys: list[str] = []
    if "station_name" in df.columns:
        keys.append("station_name")
    for k in ("station_id", "week_of_year", "year"):
        if k in df.columns:
            keys.append(k)
    if not keys:
        return df.copy()
    return df.sort_values(by=keys, ascending=True, kind="mergesort").reset_index(drop=True)


def cap_scatter_plot_rows(df: pd.DataFrame, max_rows: int = SCATTER_PLOT_MAX_POINTS) -> tuple[pd.DataFrame, bool]:
    """Alphabetical sort, then cap when needed for browser-safe scatter plots."""
    sorted_df = sort_scatter_plot_rows(df)
    if len(sorted_df) <= max_rows:
        return sorted_df, False
    return sorted_df.head(max_rows).copy(), True


def available_years(df: pd.DataFrame) -> list[int]:
    """Return sorted unique years as integers."""
    years = df["year"].dropna().astype(int).unique().tolist()
    years.sort()
    return years


def build_scatter_ready(df: pd.DataFrame) -> pd.DataFrame:
    """Build a wide frame for TMIN vs TMAX plotting with explicit plot status.

    In this project's source data, ``week_status`` is already derived from ``n_obs``
    (and related rules) when the CSV is built. ``status_tmin`` / ``status_tmax`` are
    pivoted from ``week_status`` per element, so they encode the same n_obs-based
    classification for each measure.

    ``plot_status`` still combines both element statuses with an explicit
    ``n_obs_* >= MIN_OBS_FOR_VALID_SCATTER`` check so the scatter tier stays
    aligned even if a row were ever inconsistent (defensive guardrail).

    Japan processed CSV uses ``valid_week``; it is treated as ``valid_data`` before pivot.
    """
    filtered = df[df["element"].isin(["TMIN", "TMAX"])].copy()
    filtered["week_status"] = canonicalize_week_status(filtered["week_status"])

    values_wide = (
        filtered.pivot_table(
            index=["station_id", "year", "week_of_year"],
            columns="element",
            values="weekly_mean",
            aggfunc="first",
        )
        .rename(columns={"TMIN": "tmin", "TMAX": "tmax"})
        .reset_index()
    )

    status_wide = (
        filtered.pivot_table(
            index=["station_id", "year", "week_of_year"],
            columns="element",
            values="week_status",
            aggfunc="first",
        )
        .rename(columns={"TMIN": "status_tmin", "TMAX": "status_tmax"})
        .reset_index()
    )

    obs_wide = (
        filtered.pivot_table(
            index=["station_id", "year", "week_of_year"],
            columns="element",
            values="n_obs",
            aggfunc="first",
        )
        .rename(columns={"TMIN": "n_obs_tmin", "TMAX": "n_obs_tmax"})
        .reset_index()
    )

    scatter_df = (
        values_wide.merge(status_wide, on=["station_id", "year", "week_of_year"], how="left")
        .merge(obs_wide, on=["station_id", "year", "week_of_year"], how="left")
    )

    has_no_data = (scatter_df["status_tmin"] == "no_data") | (
        scatter_df["status_tmax"] == "no_data"
    )
    has_insufficient = (scatter_df["status_tmin"] == "insufficient_data") | (
        scatter_df["status_tmax"] == "insufficient_data"
    )
    both_valid_status = (scatter_df["status_tmin"] == "valid_data") & (
        scatter_df["status_tmax"] == "valid_data"
    )
    # Matches the usual valid_data rule (>= MIN_OBS_FOR_VALID_SCATTER obs per side);
    # redundant with well-formed week_status but kept explicit for plot_status.
    both_obs_valid = (scatter_df["n_obs_tmin"] >= MIN_OBS_FOR_VALID_SCATTER) & (
        scatter_df["n_obs_tmax"] >= MIN_OBS_FOR_VALID_SCATTER
    )

    scatter_df["plot_status"] = "insufficient_data"
    scatter_df.loc[has_no_data, "plot_status"] = "no_data"
    scatter_df.loc[has_insufficient & ~has_no_data, "plot_status"] = "insufficient_data"
    scatter_df.loc[
        both_valid_status & both_obs_valid & ~has_no_data, "plot_status"
    ] = "valid_data"

    scatter_df = assign_season_column(scatter_df)

    return scatter_df[
        [
            "station_id",
            "year",
            "week_of_year",
            "season",
            "tmin",
            "tmax",
            "status_tmin",
            "status_tmax",
            "n_obs_tmin",
            "n_obs_tmax",
            "plot_status",
        ]
    ].copy()
