# %%
import sqlite3
from app.config import directories
import polars as pl
import pandas as pd

# %%

conn_main = sqlite3.connect(directories.RAW_DATA / 'grievance.db')
conn_archive = sqlite3.connect(directories.RAW_DATA / 'grievance_archive.db')


# %%

# Verify if the old draw of from the API is a subset of the complaints in the SQL dump
cursor_archive = conn_archive.cursor()
cursor_archive.execute("SELECT ticket_no FROM complaints")
archive_ticket_nos = [row[0] for row in cursor_archive.fetchall()]

cursor_main = conn_main.cursor()
cursor_main.execute("SELECT ticket_no FROM complaints")
main_ticket_nos = [row[0] for row in cursor_main.fetchall()]

missing_ticket_nos = set(archive_ticket_nos) - set(main_ticket_nos)
assert len(missing_ticket_nos) == 0
assert set(archive_ticket_nos).issubset(set(main_ticket_nos))

conn_archive.close()
conn_main.close()



# %%
# Check if the complaints in th
len(archive_ticket_nos)


# %%
# Connect to the small database
conn = sqlite3.connect(directories.RAW_DATA / "grievance_archive.db")
cur = conn.cursor()

# Attach the large database
cur.execute(f"ATTACH DATABASE '{directories.RAW_DATA / 'grievance.db'}' AS large_db;")

# Get the list of columns for the table
cur.execute("PRAGMA table_info(complaints);")
columns = [row[1] for row in cur.fetchall()]
columns = columns[1:7]
columns

# %%
# Check which rows in small.db are missing from large.db
query = f"""
SELECT s.*
FROM complaints AS s
LEFT JOIN large_db.complaints AS l
ON {" AND ".join([f"s.{c} = l.{c}" for c in columns])}
WHERE l.{columns[0]} IS NULL;
"""

cur.execute(query)
missing_rows = cur.fetchall()

if missing_rows:
    print(f"Missing rows: {len(missing_rows)}")
else:
    print("All rows in small.db are present in large.db")

# %%
# Select the rows in large db with ticket_no in main DB
query = """
SELECT *
FROM large_db.complaints
WHERE ticket_no IN (SELECT ticket_no FROM complaints);
"""

dump_df =pd.read_sql_query(query, conn)



# %%
query = """
SELECT *
FROM complaints
"""

api_df =pd.read_sql_query(query, conn)


# %%
# Same number of rows
assert api_df.shape[0] == dump_df.shape[0]



# %%
dump_df_subset = dump_df[api_df.columns]

# %%
dump_df_subset.info()


# %%
api_df.info()

# %%
dump_df_subset.describe()

# %%
dump_df_subset = dump_df_subset.sort_values(by='ticket_no').reset_index(drop=True)
api_df = api_df.sort_values(by='ticket_no').reset_index(drop=True)
dump_df_subset.drop(columns=["id"],inplace=True)
api_df.drop(columns=["id"],inplace=True)


# %%
# Check at how many points the dump and the API data differ
diff_df = dump_df_subset.fillna('').astype(str) != api_df.fillna('').astype(str)
diff_df.sum()

# %%
# Check if there are more missings in API data than dump data
dump_df_subset.isnull().sum() - api_df.isnull().sum()






# %%
cols_to_report = [ col for col in dump_df_subset.columns if col not in ["document_downloaded", "document_download_date", "document_download_error", "local_document_path"]]

# %%
diff_locs = diff_df[cols_to_report].stack()[lambda x: x]

# %%
diff_locs

# %%
diff_summary = pd.DataFrame({
    'row':[row for row, col in diff_locs.index],
    'col':[col for row, col in diff_locs.index],
    'dump_value':[dump_df_subset.at[row, col] for row, col in diff_locs.index],
    'api_value':[api_df.at[row, col] for row, col in diff_locs.index]

})



# %%

diff_summary.to_excel(directories.LOGS / "dump_api_diff_summary.xlsx", index=False)

# %%
diff_summary[diff_summary['col'] == 'document_url']


