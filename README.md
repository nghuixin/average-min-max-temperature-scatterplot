# Scatterplot showing average min and max temperatures across a 7-day period
PyShiny App with filter by Year and Season (Winter, Spring, Autumn, Summmer)


## Features

- **Scatter plot**: x = weekly mean TMIN, y = weekly mean TMAX; color = `plot_status`, which indicates if there was at least 6  `n_obs` to be considered as `valid_data`, where at least 6 data points were used to calculate the average temperature.  
- **Axis titles**: values are **tenths of degrees Celsius** (see plot labels).
- **Fixed axes for the selected year**: x/y ranges use min/max over **all plottable points for that year** (all seasons), so changing season or the display cap does not rescale the axes.
- **Year** selector and **Season** multi-select (Winter / Spring / Summer / Autumn by `week_of_year`).
- **Table**: same rows as the plot (alphabetical sort), optional column filters; includes `season`, station name, and status columns.
- **Row cap**: at most **50,000** points per view for responsiveness (deterministic sort, then head).

## Data layout

Expected **long** CSV columns (see `src/preprocessing.py`):

| Column         | Description                                      |
|----------------|--------------------------------------------------|
| `station_id`   | Station identifier                             |
| `year`         | Year                                             |
| `week_of_year` | ISO-style week index                           |
| `element`      | `TMIN` or `TMAX` (only these are loaded)       |
| `n_obs`        | Observation count used for QC                  |
| `weekly_mean`  | Weekly mean value (tenths °C in this dataset)   |
| `week_status`  | e.g. `valid_week`, `valid_data`, `insufficient_data`, `no_data` |

Bundled processed files:

- `data/processed/japan_weekly_weather.csv` — main weather file (large).
- `data/processed/japan_weekly_weather_stations.csv` — `station_id` → `name` (shown as `station_name`).

The app loads **TMIN/TMAX** rows with **year ≥ 2000** in **chunks** to limit memory use. Startup can take noticeable time on first run.

### Wide “scatter-ready” frame

`build_scatter_ready()` pivots long rows to one row per `(station_id, year, week_of_year)` with `tmin`, `tmax`, per-element statuses, `n_obs_*`, `plot_status`, and `season`.

- **`valid_week`** in the source is normalized to **`valid_data`** for logic and display.
- Top **`plot_status`** tier (`valid_data`) requires both sides **`valid_data`** and **`n_obs_tmin` / `n_obs_tmax` ≥ `MIN_OBS_FOR_VALID_SCATTER`** (default **6**).
- Points with **`no_data`** or missing **tmin/tmax** are excluded from the plot/table base.

### Seasons (by `week_of_year`)

| Season | Weeks        |
|--------|--------------|
| Winter | 1–9 and 49–53 (49–52 per calendar band; 53 if present) |
| Spring | 10–22        |
| Summer | 23–35        |
| Autumn | 36–48        |

## Project layout

```
app.py                 # PyShiny UI + server
src/preprocessing.py   # Load, pivot, seasons, plot_status, caps
data/processed/        # Japan CSVs (not committed if large — add locally)
data/sample/           # Small sample CSV for tests / dev
requirements.txt
```

## Setup

Python 3.10+ recommended.

```bash
pip install -r requirements.txt
```

Pinned stack: **Plotly 5.x** (not 6) with **ipywidgets** and **shinywidgets** for interactive Plotly in Shiny (`output_widget` + `render_widget`).

## Run

```bash
shiny run app.py
```

Or with reload during development:

```bash
shiny run --reload app.py
```

## Configuration (code constants)

In `src/preprocessing.py`:

- `DEFAULT_MIN_YEAR` — default **2000** (rows before this are not loaded from the Japan file).
- `MIN_OBS_FOR_VALID_SCATTER` — default **6** (minimum `n_obs` per element for top plot tier).
- `SCATTER_PLOT_MAX_POINTS` — default **50_000** (max points drawn per view).
- `CHUNK_ROWS` — CSV chunk size for loading.

Adjust paths in `app.py` if your data live elsewhere.

## Development notes

- Plot colors use `color_discrete_map` on `plot_status` (not `color_discrete_sequence` with a dict).
- The sample file `data/sample/weekly_climate_sample.csv` is suitable for small local tests if you temporarily point loading at it (requires code change).
