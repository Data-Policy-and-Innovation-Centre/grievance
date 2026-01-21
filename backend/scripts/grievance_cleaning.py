# grievance_cleaning.py
# ---------------------------------------------------------
# Reusable cleaning, audit, mapping, and trend utilities
# for Janasunani grievance data
# ---------------------------------------------------------

from pathlib import Path
import pandas as pd
import numpy as np
import sqlite3
import matplotlib.pyplot as plt


# ---------------------------------------------------------
# 1. Data loading
# ---------------------------------------------------------

def load_complaints(db_path: Path):
    """
    Load grievance complaints table from SQLite DB.
    """
    conn = sqlite3.connect(db_path)
    tables = pd.read_sql_query(
        "SELECT name FROM sqlite_master WHERE type='table';", conn
    )
    df = pd.read_sql_query("SELECT * FROM complaints;", conn)
    conn.close()
    return df, tables


def create_working_copy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create a safe working copy.
    """
    df_work = df.copy()
    return df_work


def select_analysis_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Retain analytically relevant columns only.
    """
    cols = [
        "id", "ticket_no", "grievance", "document_url",
        "office_id", "office", "received_by",
        "district_id", "district", "mode", "disability",
        "status", "created_on",
        "category_id", "category",
        "dept_id", "dept",
        "subcategory_id", "subcategory",
        "state", "petitioner_gender"
    ]
    return df[cols].copy()


# ---------------------------------------------------------
# 2. Missingness & basic audits
# ---------------------------------------------------------

def missing_value_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.isnull()
        .mean()
        .mul(100)
        .round(2)
        .reset_index()
        .rename(columns={"index": "column", 0: "missing_pct"})
        .sort_values("missing_pct", ascending=False)
    )

def value_counts_full(df, col):
    """
     Returns value counts including NaN.
    """
    return df[col].value_counts(dropna=False) 

def non_null_counts(df: pd.DataFrame, cols):
    return {c: df[c].notna().sum() for c in cols}


def null_counts(df: pd.DataFrame, cols):
    return {c: df[c].isna().sum() for c in cols}


def unique_values(df: pd.DataFrame, col: str):
    return df[col].unique()


def unique_combinations(df: pd.DataFrame, id_col: str, name_col: str):
    return (
        df[[id_col, name_col]]
        .value_counts(dropna=False)
        .reset_index(name="count")
    )


def type_audit(df: pd.DataFrame, col: str):
    return df[col].apply(type).value_counts()


def categorical_audit(df: pd.DataFrame, col: str):
    vc = df[col].value_counts(dropna=False)
    return pd.DataFrame({
        "value": vc.index,
        "count": vc.values,
        "percentage": (vc.values / len(df) * 100).round(2)
    })

def _crosstab(df, row, col, normalize=False):
    return pd.crosstab(
        df[row],
        df[col],
        dropna=False,
        normalize='index' if normalize else False
    )

def crosstab_counts(df, row, col):
    """
    Crosstab counts between two columns.
    """
    return _crosstab(df, row, col)


def crosstab_percent(df, row, col):
    """
    Row-normalised crosstab percentages.
    """
    return (_crosstab(df, row, col, normalize=True) * 100).round(2)

def head_rows(df, cols, n=5):
    """
    Returns first n rows of the dataframe.
    Optionally limits to specific columns.
    """
    return df[cols].head(n)

# ---------------------------------------------------------
# 3. Ticket number audits
# ---------------------------------------------------------

def ticket_length_distribution(df):
    return df['ticket_no'].astype(str).str.len().value_counts().sort_index()

def ticket_length_examples(df, n=5):
    for length in sorted(df['ticket_no'].astype(str).str.len().unique()):
        print(f"\nTicket length = {length}")
        print(
            df.loc[
                df['ticket_no'].astype(str).str.len()==length,
                'ticket_no'
            ].head(n).to_list()
        )

def ticket_length_date_range(df):
    df = df.copy()
    df['created_on'] = pd.to_datetime(df['created_on'], errors='coerce')
    df['ticket_length'] = df['ticket_no'].astype(str).str.len()
    return (
        df.groupby('ticket_length')['created_on']
          .agg(['min','max'])
          .sort_index()
    )

# ---------------------------------------------------------
# 4. Document URL audits
# ---------------------------------------------------------

# Create binary variable Yes/No for document attached
def add_document_flag(df):
    df = df.copy()
    df['document_attached'] = np.where(
        df['document_url'].notna(),'Yes','No'
    )
    return df

# Create crosstab between mode and document attached
def mode_vs_document(df):
    return pd.crosstab(
        df['mode'],
        df['document_attached'],
        normalize='index',
        margins=True
    )

# ---------------------------------------------------------
# 5. Time enrichment
# ---------------------------------------------------------

def enrich_created_on(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["created_on"] = pd.to_datetime(df["created_on"], errors="coerce")

    df["year"] = df["created_on"].dt.year
    df["month"] = df["created_on"].dt.month
    df["month_name"] = df["created_on"].dt.month_name()
    df["day"] = df["created_on"].dt.day
    df["day_of_week"] = df["created_on"].dt.day_name()
    df["hour"] = df["created_on"].dt.hour
    df["date"] = df["created_on"].dt.date

    return df


# ---------------------------------------------------------
# 6. Generic ID–Name validation
# ---------------------------------------------------------

def validate_id_name_mapping(
    df,
    id_col,
    name_col,
    ref_df,
    ref_id_col,
    ref_name_col
):
    df_check = df[[id_col, name_col]].drop_duplicates().copy()
    df_check[name_col] = (
        df_check[name_col]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    ref_df = ref_df.copy()
    ref_df[ref_name_col] = (
        ref_df[ref_name_col]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    merged = df_check.merge(
        ref_df[[ref_id_col, ref_name_col]],
        left_on=id_col,
        right_on=ref_id_col,
        how="left",
        indicator=True
    )

    merged["match_status"] = merged["_merge"].map({
        "both": "Matched",
        "left_only": "Not Matched"
    })

    return {
        "validation_table": merged.drop(columns="_merge"),
        "summary": merged["match_status"].value_counts(),
        "unmatched": merged[merged["match_status"] == "Not Matched"][
            [id_col, name_col]
        ]
    }


# ---------------------------------------------------------
# 7. Reference loaders
# ---------------------------------------------------------

def load_district_reference(path: Path):
    df = pd.read_csv(path)
    df = df[
        (df["intDemoParentValueId"] == 1) &
        (df["intSubLevelId"] == 1)
    ][["intDemoHierarchyValueId", "vchDemoHierarchyValue"]]

    return df.rename(columns={
        "intDemoHierarchyValueId": "district_id_ref",
        "vchDemoHierarchyValue": "district_ref"
    })


def load_category_reference(path: Path):
    df = pd.read_csv(path)[["intCategoryId", "vchCategory"]]
    return df.rename(columns={
        "intCategoryId": "category_id_ref",
        "vchCategory": "category_ref"
    })


def load_subcategory_reference(path: Path):
    df = pd.read_csv(path)[
        ["intSubCategoryId", "intCategoryId", "vchSubCategory"]
    ]
    return df.rename(columns={
        "intSubCategoryId": "subcategory_id_ref",
        "intCategoryId": "category_id_ref",
        "vchSubCategory": "subcategory_ref"
    })


def load_office_reference(path: Path):
    df = pd.read_csv(path)[["intOfficeId", "vchOfficeName"]]
    return df.rename(columns={
        "intOfficeId": "office_id_ref",
        "vchOfficeName": "office_ref"
    })


def load_department_reference(path: Path):
    df = pd.read_csv(path)
    df = df[df["intAdminLabelId"] == 1][
        ["intAdminHierarchyValueId", "vchAdminHierarchyValue"]
    ]
    return df.rename(columns={
        "intAdminHierarchyValueId": "dept_id_ref",
        "vchAdminHierarchyValue": "dept_ref"
    })


# ---------------------------------------------------------
# 8. Category–subcategory mappings
# ---------------------------------------------------------

##Complaint vs Admin subcategory mapping for a given category_id
def category_subcategory_mapping_with_counts(
    df_work: pd.DataFrame,
    sub_ref: pd.DataFrame,
    category_id: int,
    sort_by_count: bool = True
) -> pd.DataFrame:
    """
    Compare complaint-side and admin-side subcategory mappings
    for a given category_id, with complaint counts.
    """

    # Complaint-side mapping
    work = (
        df_work[df_work["category_id"] == category_id][
            ["subcategory_id", "subcategory"]
        ]
        .drop_duplicates()
    )

    # Admin-side mapping (USE RENAMED COLUMNS)
    admin = (
        sub_ref[sub_ref["category_id_ref"] == category_id][
            ["subcategory_id_ref", "subcategory_ref"]
        ]
        .rename(columns={
            "subcategory_id_ref": "subcategory_id",
            "subcategory_ref": "admin_subcategory"
        })
    )

    # Merge complaint ↔ admin
    merged = work.merge(admin, on="subcategory_id", how="outer")

    # Complaint counts
    counts = (
        df_work[df_work["category_id"] == category_id]
        .groupby("subcategory_id")
        .size()
        .reset_index(name="count")
    )

    merged = merged.merge(counts, on="subcategory_id", how="left")
    merged["count"] = merged["count"].fillna(0).astype(int)

    out = merged[
        ["subcategory_id", "subcategory", "admin_subcategory", "count"]
    ]

    if sort_by_count:
        out = out.sort_values(["count", "subcategory_id"], ascending=[False, True])

    return out.reset_index(drop=True)


##Complaint vs Admin subcategory mapping WITH admin category validation
def category_subcategory_mapping(
    df_work: pd.DataFrame,
    sub_ref: pd.DataFrame,
    cat_ref: pd.DataFrame,
    category_id: int
) -> pd.DataFrame:
    """
    Complaint vs admin subcategory mapping with:
    - admin category validation
    - complaint counts
    """

    # Complaint-side mapping
    work = (
        df_work[df_work["category_id"] == category_id][
            ["category_id", "category", "subcategory_id", "subcategory"]
        ]
        .drop_duplicates()
    )

    # Admin-side subcategories
    admin_sub = sub_ref.rename(columns={
        "subcategory_id_ref": "subcategory_id",
        "category_id_ref": "admincategory_id",
        "subcategory_ref": "admin_subcategory"
    })

    merged = work.merge(admin_sub, on="subcategory_id", how="left")

    # Complaint counts
    counts = (
        df_work[df_work["category_id"] == category_id]
        .groupby("subcategory_id")
        .size()
        .reset_index(name="count")
    )

    merged = merged.merge(counts, on="subcategory_id", how="left")
    merged["count"] = merged["count"].fillna(0).astype(int)

    # Admin category names
    admin_cat = cat_ref.rename(columns={
        "category_id_ref": "admincategory_id",
        "category_ref": "admin_category"
    })

    merged = merged.merge(admin_cat, on="admincategory_id", how="left")

    return (
        merged[
            [
                "category_id", "category",
                "subcategory_id", "subcategory",
                "admincategory_id", "admin_category",
                "admin_subcategory", "count"
            ]
        ]
        .sort_values(["count", "subcategory_id"], ascending=[False, True])
        .reset_index(drop=True)
    )



# ---------------------------------------------------------
# 9. Time-series trends
# ---------------------------------------------------------

def build_monthly_trend(
    df: pd.DataFrame,
    subcategory_id: int,
    rolling_window: int = 3
):
    df_sub = df[df["subcategory_id"] == subcategory_id].copy()
    df_sub = df_sub.dropna(subset=["year", "month"])

    df_sub["year"] = df_sub["year"].astype(int)
    df_sub["month"] = df_sub["month"].astype(int)

    df_sub["year_month"] = (
        df_sub["year"].astype(str) + "-" +
        df_sub["month"].apply(lambda m: f"{m:02d}")
    )

    monthly = (
        df_sub.groupby("year_month")["ticket_no"]
        .nunique()
        .reset_index(name="complaint_count")
        .sort_values("year_month")
    )

    monthly["rolling_3mo_avg"] = (
        monthly["complaint_count"]
        .rolling(rolling_window, min_periods=1)
        .mean()
        .round(2)
    )

    return monthly.reset_index(drop=True)


def plot_single_trend(monthly_df, title):
    plt.figure(figsize=(12, 5))
    plt.plot(monthly_df["year_month"], monthly_df["complaint_count"], marker="o")
    plt.plot(
        monthly_df["year_month"],
        monthly_df["rolling_3mo_avg"],
        linestyle="--",
        marker="o"
    )
    plt.xticks(rotation=90)
    plt.title(title)
    plt.xlabel("Year-Month")
    plt.ylabel("Complaints")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()
