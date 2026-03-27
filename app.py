from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
from shiny import App, reactive, render, ui
from shinywidgets import output_widget, render_widget

from src.preprocessing import (
    ALL_SEASONS,
    MIN_OBS_FOR_VALID_SCATTER,
    SCATTER_PLOT_MAX_POINTS,
    available_years,
    build_scatter_ready,
    cap_scatter_plot_rows,
    load_japan_weekly_tmin_tmax,
    load_station_names,
    merge_station_names,
)


BASE_DIR = Path(__file__).parent
WEATHER_DATA_PATH = os.getenv(
    "WEATHER_DATA_PATH",
    str(BASE_DIR / "data" / "processed" / "japan_weekly_weather.csv"),
)
STATIONS_DATA_PATH = os.getenv(
    "STATIONS_DATA_PATH",
    str(BASE_DIR / "data" / "processed" / "japan_weekly_weather_stations.csv"),
)


weekly_df = load_japan_weekly_tmin_tmax(WEATHER_DATA_PATH)
scatter_df = build_scatter_ready(weekly_df)
scatter_df["year"] = pd.to_numeric(scatter_df["year"], errors="coerce").astype(int)
stations_df = load_station_names(STATIONS_DATA_PATH)
scatter_df = merge_station_names(scatter_df, stations_df)
scatter_plot_base = scatter_df[
    (scatter_df["plot_status"] != "no_data")
    & scatter_df["tmin"].notna()
    & scatter_df["tmax"].notna()
].copy()
year_choices = available_years(scatter_plot_base)
year_choice_map = {str(year): str(year) for year in year_choices}
default_year = str(year_choices[-1]) if year_choices else None

season_choice_map = {s: s for s in ALL_SEASONS}


def pad_axis_range(lo: float, hi: float, pad_frac: float = 0.02) -> tuple[float, float]:
    """Small padding so points are not flush on the axis edges."""
    if lo > hi:
        lo, hi = hi, lo
    if lo == hi:
        span = abs(lo) if lo != 0 else 1.0
        return lo - span * 0.05, hi + span * 0.05
    span = hi - lo
    return lo - pad_frac * span, hi + pad_frac * span


app_ui = ui.page_fluid(
    ui.h2("Weekly Average Min and Max Temperature in Japan 日本の週間平均最低・最高気温"),
    ui.layout_columns(
        ui.input_selectize(
            "year",
            "Year",
            choices=year_choice_map,
            selected=default_year,
            multiple=False,
        ),
        ui.input_selectize(
            "season",
            "Season",
            choices=season_choice_map,
            selected=list(ALL_SEASONS),
            multiple=True,
        ),
        col_widths=[6, 6],
    ),
    ui.layout_columns(
        ui.card(
          #  ui.card_header("TMIN vs TMAX (Japan weekly)"),
            ui.output_text_verbatim("scatter_counts"),
            output_widget("scatter_plot", height="420px"),
        ),
        ui.card(
            ui.card_header("Table (same rows as plot, alphabetical)"),
            ui.output_data_frame("weekly_table"),
        ),
        col_widths=[6, 6],
    ),
    ui.p(
        "Seasons by week_of_year: Winter 1–9 and 49–52; Spring 10–22; Summer 23–35; "
        "Autumn 36–48. Note: source week_status is derived from n_obs; valid_week is "
        "treated as valid_data. plot_status top tier requires valid_data on both sides "
        f"and n_obs ≥ {MIN_OBS_FOR_VALID_SCATTER} each. Years ≥ 2000. "
        f"Scatter cap {SCATTER_PLOT_MAX_POINTS:,} points per view."
    ),
)


def server(input, output, session):
    @reactive.calc
    def selected_year() -> int | None:
        value = input.year()
        if value is None or value == "":
            return None
        return int(value)

    @reactive.calc
    def selected_seasons() -> list[str]:
        sel = input.season()
        if sel is None or sel == "":
            return list(ALL_SEASONS)
        if isinstance(sel, (list, tuple)):
            return [str(s) for s in sel]
        return [str(sel)]

    @reactive.calc
    def filtered_scatter():
        year = selected_year()
        seasons = selected_seasons()
        if year is None:
            return scatter_plot_base.iloc[0:0].copy()
        df = scatter_plot_base[scatter_plot_base["year"] == year].copy()
        if not seasons:
            return df.iloc[0:0].copy()
        return df[df["season"].isin(seasons)].copy()

    @reactive.calc
    def plotted_scatter_df():
        """Same rows, order, and cap as the scatter plot (alphabetical sort, then cap)."""
        df = filtered_scatter()
        if df.empty:
            return df
        plot_df = df[df["tmin"].notna() & df["tmax"].notna()].copy()
        if plot_df.empty:
            return plot_df
        plot_df, _ = cap_scatter_plot_rows(plot_df, SCATTER_PLOT_MAX_POINTS)
        return plot_df

    @reactive.calc
    def year_tmin_tmax_axis_range():
        """
        Axis bounds from all plottable points for the selected year (all seasons),
        so zoom does not change when season filter or plot cap changes.
        """
        year = selected_year()
        if year is None:
            return None
        ydf = scatter_plot_base[scatter_plot_base["year"] == year]
        if ydf.empty:
            return None
        tmin = pd.to_numeric(ydf["tmin"], errors="coerce")
        tmax = pd.to_numeric(ydf["tmax"], errors="coerce")
        if not tmin.notna().any() or not tmax.notna().any():
            return None
        return {
            "x": (float(tmin.min()), float(tmin.max())),
            "y": (float(tmax.min()), float(tmax.max())),
        }

    @output
    @render.text
    def scatter_counts():
        year = selected_year()
        seasons = selected_seasons()
        if year is None:
            return "No year selected."
        if not seasons:
            return "Select at least one season."
        year_rows = scatter_df[scatter_df["year"] == year]
        sf = year_rows[year_rows["season"].isin(seasons)]
        plottable = sf[
            (sf["plot_status"] != "no_data")
            & sf["tmin"].notna()
            & sf["tmax"].notna()
        ]
        capped, was_capped = cap_scatter_plot_rows(plottable, SCATTER_PLOT_MAX_POINTS)
        cap_note = (
            f" | Plot uses {len(capped)} of {len(plottable)} points (capped)"
            if was_capped
            else f" | Plot uses all {len(plottable)} points"
        )
        return (
            f"Year rows: {len(year_rows)} | Season-filtered: {len(sf)} | "
            f"Plottable: {len(plottable)}{cap_note}"
        )

    @output
    @render_widget
    def scatter_plot():
        plot_df = plotted_scatter_df()
        full_year = filtered_scatter()
        if plot_df.empty:
            if full_year.empty:
                return px.scatter(title="No data for selected year/season")
            return px.scatter(title="No complete TMIN/TMAX pairs for selection")

        plottable_n = len(full_year)
        was_capped = len(plot_df) < plottable_n
      #  title = "TMIN vs TMAX"
       # if was_capped:
       #     title = f"TMIN vs TMAX (showing {len(plot_df):,} of {plottable_n:,} points)"

        hover = ["station_id", "station_name", "season", "week_of_year", "year"]
        hover = [c for c in hover if c in plot_df.columns]

        fig = px.scatter(
            plot_df,
            x="tmin",
            y="tmax",
            color="plot_status",
            color_discrete_map={
                "valid_data": "green",
                "insufficient_data": "blue",
            },
            hover_data=hover,
          #  title=title,
            labels={
                "tmin": "Avg min temp over 7 days (tenths of degrees C)",
                "tmax": "Avg max temp over 7 days (tenths of degrees C)",
            },
        )
        bounds = year_tmin_tmax_axis_range()
        if bounds is not None:
            x0, x1 = pad_axis_range(bounds["x"][0], bounds["x"][1])
            y0, y1 = pad_axis_range(bounds["y"][0], bounds["y"][1])
            fig.update_xaxes(range=[x0, x1], autorange=False)
            fig.update_yaxes(range=[y0, y1], autorange=False)
        return fig

    @output
    @render.data_frame
    def weekly_table():
        columns = [
            "station_id",
            "station_name",
            "year",
            "season",
            "week_of_year",
            "tmin",
            "tmax",
            "status_tmin",
            "status_tmax",
            "plot_status",
        ]
        wide_df = plotted_scatter_df()
        columns = [c for c in columns if c in wide_df.columns]
        return render.DataGrid(wide_df[columns], filters=True)


app = App(app_ui, server)
