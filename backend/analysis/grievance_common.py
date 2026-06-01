"""
grievance_common.py
===================
Single shared module for the entire grievance-analysis notebook suite.

Every notebook does `from grievance_common import *` and then calls the
functions below. All shared code lives here exactly once: configuration,
data loading, date / financial-year logic, the analysis-window filter,
district-name standardization, population reference data, status grouping,
escalation-route reconstruction, office-name standardization, generic
table helpers, and the district choropleth.

Single data source
-------------------
The whole suite reads ONE database, `grievance_with_routes.db`, which holds
both the `complaints` table and the `action_history` table.

"""

from __future__ import annotations

import os
import re
import sqlite3

import numpy as np
import pandas as pd

__all__ = [
    # config
    "BASE_DIR", "DB_PATH", "DISTRICT_SHAPEFILE", "BLOCK_SHAPEFILE",
    "OUTPUT_DIR", "EXCEL_DIR", "ANALYSIS_START", "ANALYSIS_END",
    "FOCUS_YEAR", "VALID_YEARS", "MAP_YEARS", "ONLINE_MODES",
    "HOUSING_SUBCATS", "DISTRICT_NAME_FIX", "PMAY_NAME", "RURAL_NAME",
    "STATUS_ORDER",
    # data loading
    "load_table", "load_complaints", "load_action_history",
    "add_time_fields", "filter_window", "compute_disposal_days",
    # reference data
    "population_df",
    # geo
    "load_district_shapefile", "standardize_districts", "draw_choropleth",
    # status / mode
    "clean_series", "make_explicit_nan", "status_bucket", "status_group",
    "add_mode_group",
    # routes / offices
    "authority_from_status", "compress_sequence", "clean_authority",
    "build_routes", "standardize_office"
    # generic table helpers
    "unique_counts", "add_total_row", "yearly_counts", "pivot_count_pct",
]

# ======================================================================
# CONFIGURATION  -- edit paths here only
# ======================================================================
BASE_DIR = "/Users/ghazalhashmi/Library/CloudStorage/Box-Box/Ghazal"

# Single source database: holds `complaints` AND `action_history`.
DB_PATH = os.path.join(BASE_DIR, "Data/Raw/grievance_with_routes.db")

# Shapefiles
DISTRICT_SHAPEFILE = os.path.join(
    BASE_DIR, "Data/shapefile/district/Odisha_Admin_District_BND_2021.shp")
BLOCK_SHAPEFILE = os.path.join(
    BASE_DIR, "Data/shapefile/block/Odisha_Admin_Block_BND_2021.shp")

# Output folders
OUTPUT_DIR = os.path.join(BASE_DIR, "Outputs/January Output")
EXCEL_DIR = os.path.join(BASE_DIR, "12th feb/excel sheets")

for _d in (OUTPUT_DIR, EXCEL_DIR):
    os.makedirs(_d, exist_ok=True)

# Analysis parameters
ANALYSIS_START = "2021-07-01"          # inclusive
ANALYSIS_END = "2025-07-01"            # exclusive
FOCUS_YEAR = "2024-2025"
VALID_YEARS = ["2021-2022", "2022-2023", "2023-2024", "2024-2025"]
MAP_YEARS = ["2023-2024", "2024-2025"]

ONLINE_MODES = {"Website", "Mobile", "Whatsapp", "Email", "Twitter",
                "Facebook"}
HOUSING_SUBCATS = ["Rural Housing", "IAY/MKY/BPGY/PMAY"]
PMAY_NAME = "IAY/MKY/BPGY/PMAY"
RURAL_NAME = "Rural Housing"

# Canonical status-group display order.
STATUS_ORDER = ["Discard", "Disposed with Benefit", "Disposed", "Open"]

# Shapefile district spellings -> dataset spellings (uppercased).
DISTRICT_NAME_FIX = {
    "ANUGUL": "ANGUL",
    "BARAGARH": "BARGARH",
    "BOLANGIR": "BALANGIR",
    "JAGATSINGPUR": "JAGATSINGHAPUR",
    "KEONJHAR": "KENDUJHAR",
    "KHURDA": "KHORDHA",
    "KENDRAPADA": "KENDRAPARA",
    "NAWARANGPUR": "NABARANGPUR",
    "MALKANAGIRI": "MALKANGIRI",
    "SONEPUR": "SUBARNAPUR",
}


# ======================================================================
# DATA LOADING
# ======================================================================
def load_table(table: str, db_path: str = DB_PATH) -> pd.DataFrame:
    """Load any table from the single source database."""
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql(f"SELECT * FROM {table}", conn)


def load_complaints(db_path: str = DB_PATH) -> pd.DataFrame:
    """Load the `complaints` table with date columns parsed."""
    df = load_table("complaints", db_path)
    if "created_on" in df.columns:
        df["created_on"] = pd.to_datetime(df["created_on"], errors="coerce")
    if "resolved_on" in df.columns:
        df["resolved_on"] = pd.to_datetime(df["resolved_on"], errors="coerce")
    return df


def load_action_history(db_path: str = DB_PATH) -> pd.DataFrame:
    """Load the `action_history` table with the action date parsed."""
    ah = load_table("action_history", db_path)
    if "action_taken_date" in ah.columns:
        ah["action_taken_date"] = pd.to_datetime(
            ah["action_taken_date"], errors="coerce")
    return ah


def add_time_fields(df: pd.DataFrame, date_col: str = "created_on"
                    ) -> pd.DataFrame:
    """Add year, month, year_month, and custom_year (July-June FY) columns."""
    out = df.copy()
    out["year"] = out[date_col].dt.year
    out["month"] = out[date_col].dt.month
    out["year_month"] = out[date_col].dt.to_period("M").astype(str)
    out["custom_year"] = np.where(
        out["month"] >= 7,
        out["year"].astype("Int64").astype(str) + "-"
        + (out["year"] + 1).astype("Int64").astype(str),
        (out["year"] - 1).astype("Int64").astype(str) + "-"
        + out["year"].astype("Int64").astype(str),
    )
    return out


def filter_window(df: pd.DataFrame, start: str = ANALYSIS_START,
                  end: str = ANALYSIS_END, date_col: str = "created_on",
                  explicit_nan_cols=("office", "dept", "category",
                                     "subcategory", "district", "status"),
                  ) -> pd.DataFrame:
    """Filter to the analysis window and make missing categoricals explicit."""
    out = df[(df[date_col] >= start) & (df[date_col] < end)].copy()
    for col in explicit_nan_cols:
        if col in out.columns:
            out[col] = out[col].fillna("NaN")
    return out


def compute_disposal_days(df: pd.DataFrame, drop_negative: bool = True
                            ) -> pd.DataFrame:
    """Add `disposal_days` = resolved_on - created_on, in days."""
    out = df.copy()
    out["disposal_days"] = (
        (out["resolved_on"] - out["created_on"]).dt.total_seconds()
        / (24 * 3600)
    )
    if drop_negative:
        out = out[~(out["disposal_days"] < 0)].copy()
    return out


# ======================================================================
# REFERENCE DATA
# ======================================================================
def population_df() -> pd.DataFrame:
    """District population (2021 census)."""
    data = {
        "district": [
            "Angul", "Baleswar", "Bargarh", "Bhadrak", "Balangir", "Boudh",
            "Cuttack", "Deogarh", "Dhenkanal", "Gajapati", "Ganjam",
            "Jagatsinghapur", "Jajpur", "Jharsuguda", "Kalahandi",
            "Kandhamal", "Kendrapara", "Kendujhar", "Khordha", "Koraput",
            "Malkangiri", "Mayurbhanj", "Nabarangpur", "Nayagarh",
            "Nuapada", "Puri", "Rayagada", "Sambalpur", "Subarnapur",
            "Sundargarh",
        ],
        "population_2021_thousands": [
            1396, 2574, 1546, 1674, 1763, 489, 2803, 342, 1261, 616, 3829,
            1189, 1991, 622, 1753, 807, 1524, 1975, 2600, 1501, 692, 2764,
            1382, 1002, 654, 1832, 1062, 1120, 651, 2282,
        ],
    }
    pop = pd.DataFrame(data)
    pop["population_2021"] = pop["population_2021_thousands"] * 1000
    pop["district_clean"] = pop["district"].str.strip().str.upper()
    return pop


# ======================================================================
# GEOSPATIAL HELPERS
# ======================================================================
def load_district_shapefile(path: str = DISTRICT_SHAPEFILE):
    """Load the district shapefile with a standardized 'district_clean'."""
    import geopandas as gpd
    gdf = gpd.read_file(path)
    return standardize_districts(gdf, src_col="district_n")


def standardize_districts(gdf, src_col: str = "district_n"):
    """Add standardized 'district_shp' and 'district_clean' columns."""
    out = gdf.copy()
    out["district_shp"] = out[src_col].astype(str).str.strip().str.upper()
    out["district_clean"] = out["district_shp"].replace(DISTRICT_NAME_FIX)
    return out


def draw_choropleth(map_gdf, value_col, title, cbar_label, vmin=None,
                    vmax=None, fmt="%.1f", cmap="YlOrRd",
                    label_col="district_clean", diverging=False):
    """Single district choropleth with a horizontal colorbar.

    Used by every notebook that draws a district map. Set `diverging=True`
    for difference maps (color scale centered at zero).
    """
    import matplotlib.pyplot as plt
    import matplotlib as mpl

    vals = pd.to_numeric(map_gdf[value_col], errors="coerce")
    if vmin is None:
        vmin = float(np.nanmin(vals.values))
    if vmax is None:
        vmax = float(np.nanmax(vals.values))
    if diverging:
        bound = max(abs(vmin), abs(vmax))
        norm = mpl.colors.TwoSlopeNorm(vmin=-bound, vcenter=0, vmax=bound)
    else:
        norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)

    fig, ax = plt.subplots(figsize=(12, 12), dpi=200)
    map_gdf.plot(column=value_col, cmap=cmap, norm=norm, linewidth=0.5,
                 edgecolor="black", ax=ax,
                 missing_kwds={"color": "lightgrey"})
    ax.set_title(title, fontsize=15, fontweight="bold")
    ax.axis("off")

    for _, row in map_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        pt = geom.representative_point()
        name = row.get(label_col, "")
        ax.text(pt.x, pt.y, str(name).title(), ha="center", va="center",
                fontsize=7)

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="horizontal",
                        fraction=0.04, pad=0.04)
    cbar.ax.xaxis.set_major_formatter(mpl.ticker.FormatStrFormatter(fmt))
    cbar.set_label(cbar_label, fontsize=11)
    plt.show()


# ======================================================================
# STATUS / MODE HELPERS
# ======================================================================
def clean_series(s: pd.Series, fill: str = "NaN", lower: bool = False
                 ) -> pd.Series:
    """Fill missing, cast to str, strip whitespace; optionally lowercase."""
    s = s.fillna(fill).astype(str).str.strip()
    return s.str.lower() if lower else s


def make_explicit_nan(df: pd.DataFrame, cols, fill: str = "NaN"
                      ) -> pd.DataFrame:
    """Return a copy with `cols` missing values filled by `fill`."""
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = out[col].fillna(fill)
    return out



def status_bucket(status: pd.Series, benefitted: pd.Series) -> pd.Series:
    """
    Disposal/resolution-time status grouping.
 
    Four buckets matching the statuses that actually appear in the
    resolution data:
    - Discard
    - Disposed with Benefit  (status == Disposed AND benefitted == Yes)
    - Disposed               (status == Disposed AND benefitted == No)
    - In Follow Up With Close
 
    "In Follow Up With Open" gets NaN and is excluded automatically from
    any groupby (those tickets have no resolved_on date so disposal days
    is not meaningful).
    """
    s = status.fillna("").astype(str).str.strip()
    b = benefitted.fillna("").astype(str).str.strip()
 
    out = pd.Series(np.nan, index=status.index, dtype="object")
 
    out[s == "Discard"] = "Discard"
 
    disposed = s == "Disposed"
    out[disposed & (b == "Yes")] = "Disposed with Benefit"
    out[disposed & (b == "No")] = "Disposed"
 
    out[s == "In Follow Up With Close"] = "In Follow Up With Close"
 
    return out

def status_group(status: pd.Series, benefitted: pd.Series) -> pd.Series:
    """
    General status grouping.

    Labels:
    - Discard
    - Disposed with Benefit
    - Disposed
    - Open
    """

    s = status.fillna("").astype(str).str.strip()
    b = benefitted.fillna("").astype(str).str.strip()

    out = pd.Series("Open", index=status.index, dtype="object")

    out[s == "Discard"] = "Discard"

    disposed = s == "Disposed"
    out[disposed & (b == "Yes")] = "Disposed with Benefit"
    out[disposed & (b == "No")] = "Disposed"

    return out


def add_mode_group(frame: pd.DataFrame, mode_col: str = "mode"
                   ) -> pd.DataFrame:
    """Add an ordered Online/Offline 'mode_group' column (returns a copy)."""
    out = frame.copy()
    out[mode_col] = out[mode_col].fillna("NaN").astype(str).str.strip()
    out["mode_group"] = np.where(out[mode_col].isin(ONLINE_MODES),
                                 "Online", "Offline")
    out["mode_group"] = pd.Categorical(out["mode_group"],
                                       ["Online", "Offline"], ordered=True)
    return out


# ======================================================================
# ROUTE / OFFICE HELPERS
# ======================================================================
def authority_from_status(row) -> str:
    """Acting authority for one action-history row.

    Prefers the text after ' - ' in complaint_status_with_authority,
    otherwise falls back to action_taken_by.
    """
    s = row.get("complaint_status_with_authority")
    by = row.get("action_taken_by")
    s = "" if pd.isna(s) else str(s).strip()
    by = "" if pd.isna(by) else str(by).strip()
    if " - " in s:
        return s.split(" - ", 1)[1].strip()
    return by


def compress_sequence(seq) -> list:
    """Collapse consecutive duplicates and drop blanks; returns a list."""
    out = []
    for x in seq:
        x = "" if pd.isna(x) else str(x).strip()
        if x == "":
            continue
        if not out or out[-1] != x:
            out.append(x)
    return out


def clean_authority(x: str) -> str:
    """Uppercase, strip district/block suffix, normalize common variants."""
    s = "" if pd.isna(x) else str(x).strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    # keep designation only before first comma
    if "," in s:
        s = s.split(",", 1)[0].strip()
    s = s.upper()
    s = s.replace("COLLECTOR & DM",          "COLLECTOR")
    s = s.replace("COLLECTOR AND DM",         "COLLECTOR")
    s = s.replace("B.D.O",                    "BDO")
    s = s.replace("BLOCK DEVELOPMENT OFFICER","BDO")
    s = s.replace("CHIEF MINISTER",           "CM")
    s = s.replace("CM GRIEVANCE CELL",        "CM GRIEVANCE CELL")  # keep as-is
    s = s.replace("CMO",                      "CM")
    s = re.sub(r"\s{2,}", " ", s).strip(" -_/,")
    return s


def build_routes(action: pd.DataFrame, ticket_ids) -> pd.DataFrame:
    """Per-ticket escalation route for the given ticket ids.

    Returns route_list, route_tuple, route_string, route_length.
    authority_clean is uppercased and district/block suffixes are stripped
    so that route strings are comparable across districts.
    """
    ah = action[action["ticket_no"].isin(ticket_ids)].copy()

    if "action_taken_date" in ah.columns:
        ah["action_taken_date"] = pd.to_datetime(
            ah["action_taken_date"], errors="coerce")
        sort_cols = [c for c in ["ticket_no", "action_taken_date", "id"]
                     if c in ah.columns]
        ah = ah.sort_values(sort_cols)

    # step 1: extract raw authority
    ah["authority_raw"] = ah.apply(authority_from_status, axis=1)

    # step 2: clean + normalize (strips district/block names, uppercases)
    ah["authority_clean"] = ah["authority_raw"].apply(clean_authority)

    # step 3: drop rows with missing date or empty authority
    ah = ah[
        ah["action_taken_date"].notna() &
        (ah["authority_clean"] != "")
    ].copy()

    # step 4: compress consecutive same authorities + build route
    routes = (
        ah.groupby("ticket_no")["authority_clean"]
          .apply(lambda s: compress_sequence(s.tolist()))
          .reset_index(name="route_list")
    )
    routes["route_tuple"]  = routes["route_list"].apply(tuple)
    routes["route_string"] = routes["route_tuple"].apply(
        lambda t: " \u2192 ".join(t))
    routes["route_length"] = routes["route_tuple"].apply(len)
    return routes


_OFFICE_RULES = {
    "OFFICE OF CHIEF MINISTER": "CHIEF MINISTER",
    "CHIEF MINISTER'S OFFICE": "CHIEF MINISTER",
    "CM OFFICE": "CHIEF MINISTER",
    "OFFICE OF CM": "CHIEF MINISTER",
    "CM GRIEVANCE CELL": "CHIEF MINISTER",
    "OFFICE OF THE CHIEF MINISTER": "CHIEF MINISTER",
    "COLLECTOR & DM": "COLLECTOR",
    "DISTRICT COLLECTOR": "COLLECTOR",
    "COLLECTORATE": "COLLECTOR",
    "BLOCK DEVELOPMENT OFFICER": "BDO",
    "BDO OFFICE": "BDO",
    "OFFICE OF BDO": "BDO",
}


def standardize_office(x):
    """Harmonize an office/authority name to a canonical label."""
    if pd.isna(x):
        return np.nan
    x = re.sub(r"\s+", " ", str(x).upper().strip())
    x_base = x.split(",")[0].strip()
    if x in _OFFICE_RULES:
        return _OFFICE_RULES[x]
    if x_base in _OFFICE_RULES:
        return _OFFICE_RULES[x_base]
    if "CHIEF MINISTER" in x or re.search(r"\bCM\b", x):
        return "CHIEF MINISTER"
    if "COLLECTOR" in x:
        return "COLLECTOR"
    if "BLOCK DEVELOPMENT OFFICER" in x or re.search(r"\bBDO\b", x):
        return "BDO"
    return x_base


# ======================================================================
# GENERIC TABLE HELPERS
# ======================================================================
def unique_counts(df: pd.DataFrame, group_cols, ticket_col: str = "ticket_no",
                  count_name: str = "complaint_count") -> pd.DataFrame:
    """Unique-ticket counts by group, with a within-first-column pct."""
    if isinstance(group_cols, str):
        group_cols = [group_cols]
    agg = (
        df.groupby(group_cols, dropna=False)[ticket_col]
          .nunique().reset_index(name=count_name)
    )
    if len(group_cols) > 1:
        denom = agg.groupby(group_cols[0])[count_name].transform("sum")
    else:
        denom = agg[count_name].sum()
    agg["complaint_pct"] = (agg[count_name] / denom * 100).round(2)
    return agg


def add_total_row(df: pd.DataFrame, label_col: str,
                  count_col: str = "complaint_count") -> pd.DataFrame:
    """Append a 'Total' row summing `count_col`."""
    total = pd.DataFrame({
        label_col: ["Total"],
        count_col: [df[count_col].sum()],
        "complaint_pct": [100.0],
    })
    return pd.concat([df, total], ignore_index=True)


def yearly_counts(df: pd.DataFrame, group_col: str,
                  year_col: str = "custom_year",
                  ticket_col: str = "ticket_no") -> pd.DataFrame:
    """Counts of `group_col` per year plus percentage within each year."""
    counts = (
        df.groupby([group_col, year_col])[ticket_col]
          .nunique().reset_index(name="count")
    )
    year_totals = df.groupby(year_col)[ticket_col].nunique()
    counts["total_cases"] = counts[year_col].map(year_totals)
    counts["percentage"] = (counts["count"] / counts["total_cases"]
                            * 100).round(2)
    return counts


def pivot_count_pct(long_df: pd.DataFrame, index_cols,
                    year_col: str = "custom_year",
                    values=("count", "percentage")) -> pd.DataFrame:
    """Pivot a long count/pct table to (year -> count, percentage)."""
    return (
        long_df.pivot(index=index_cols, columns=year_col,
                      values=list(values))
               .swaplevel(0, 1, axis=1)
               .sort_index(axis=1)
    )