# %%
from pathlib import Path
import duckdb
import pandas as pd

db_path = Path("data/raw/grievance.db")

con = duckdb.connect(db_path)

cur = con.cursor()

# %%
res = cur.execute(f"PRAGMA table_info(complaints)")
res.df()

# %% [markdown]
# # General indicators

# %%
# Total complaints
total_complaints = cur.execute("""
SELECT ticket_no
FROM complaints
""").df()

len(total_complaints)

# %%
# Average resolution time
avg_resolution_time = cur.execute(f"""
SELECT ROUND(AVG(DATEDIFF('day', created_on, resolved_on)), 0) AS resolution_time,
       ROUND(MEDIAN(DATEDIFF('day', created_on, resolved_on)), 0) AS median
FROM complaints
WHERE resolved_on IS NOT NULL;
""").df()

avg_resolution_time

# %% [markdown]
# ## Why? Resolution times

# %%
count_by_status = cur.execute(f"""
SELECT (resolved_on IS NOT NULL) as disposed, COUNT(*) as count
FROM complaints
GROUP BY disposed
""").df()

count_by_status['pct'] = round(count_by_status['count'] / count_by_status['count'].sum()*100, 1)
count_by_status

# %%
avg_resolution_time_by_benefitted = cur.execute(f"""
SELECT benefitted,
        ROUND(AVG(DATEDIFF('day', created_on, resolved_on)), 1) AS resolution_time,
        ROUND(MEDIAN(DATEDIFF('day', created_on, resolved_on)), 1) AS median
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY benefitted
ORDER BY resolution_time DESC;
""").df()
avg_resolution_time_by_benefitted

# %%
dept = cur.execute(f"""
SELECT dept, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY dept
""").df()
dept

# %%
benefitted = cur.execute(f"""
SELECT benefitted, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY benefitted
""").df()
benefitted

# %%
top10 = cur.execute(f"""
SELECT category, subcategory, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY category, subcategory
ORDER BY count DESC
""").df()

top10['pct'] = round(top10['count'] / top10['count'].sum()*100, 1)
top10

# %%
monthly_complaints = cur.execute("""
SELECT YEAR(created_on) as year, MONTH(created_on) as month, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY year, month
ORDER BY year ASC, month ASC
""").df()

monthly_complaints

# %%
housing_monthly = cur.execute("""
SELECT YEAR(created_on) as year, MONTH(created_on) as month, COUNT(*) as count
FROM complaints
WHERE (subcategory == 'Rural Housing' OR subcategory == 'IAY/MKY/BPGY/PMAY') AND resolved_on IS NOT NULL
GROUP BY year, month
ORDER BY year ASC, month ASC
""").df()

housing_monthly

# %% [markdown]
# ### Average resolution time

# %%
avg_resolution_time_by_category = cur.execute(f"""
SELECT category, subcategory, 
        ROUND(AVG(DATEDIFF('day', created_on, resolved_on)), 1) AS resolution_time,
        ROUND(MEDIAN(DATEDIFF('day', created_on, resolved_on)), 1) AS median
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY category, subcategory
ORDER BY resolution_time DESC;
""").df()


# %%
avg_resolution_time_by_category

# %%
top10.merge(avg_resolution_time_by_category, how='left', on=['category', 'subcategory'])

# %%
modes = cur.execute(f"""
SELECT mode, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY mode
ORDER BY count DESC
""").df()


modes['pct'] = round(modes['count'] / modes['count'].sum()*100, 1)
modes

# %%
avg_resolution_time_by_mode = cur.execute(f"""
SELECT mode, 
        ROUND(AVG(DATEDIFF('day', created_on, resolved_on)), 1) AS resolution_time,
        ROUND(MEDIAN(DATEDIFF('day', created_on, resolved_on)), 1) AS median
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY mode
ORDER BY resolution_time DESC;
""").df()

avg_resolution_time_by_mode

# %%
modes.merge(avg_resolution_time_by_mode, how='left', on='mode')[['mode','count','pct', 'resolution_time']]

# %%
offices = cur.execute(f"""
SELECT office, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY office
ORDER BY count DESC
""").df()


offices['pct'] = round(offices['count'] / offices['count'].sum()*100, 1)
offices

# %%
avg_resolution_time_by_office = cur.execute(f"""
SELECT office, 
        ROUND(AVG(DATEDIFF('day', created_on, resolved_on)), 1) AS resolution_time,
        ROUND(MEDIAN(DATEDIFF('day', created_on, resolved_on)), 1) AS median
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY office
ORDER BY resolution_time DESC;
""").df()

avg_resolution_time_by_office

# %%
offices.merge(avg_resolution_time_by_office, how='left', on='office')[['office','count','pct', 'resolution_time']]

# %%
# Resolution time by mode
avg_resolution_time_by_mode = cur.execute(f"""
SELECT ROUND(AVG(DATEDIFF('day', created_on, resolved_on)), 1) AS resolution_time,
       ROUND(MEDIAN(DATEDIFF('day', created_on, resolved_on)), 1) AS median,
       CASE 
        WHEN mode == 'Mobile' OR mode == 'Whatsapp' OR mode == 'Website' THEN 'Online'
        WHEN mode == 'CM Weekly Grievance' OR mode == 'Physical' OR mode == 'Joint Hearing' THEN 'In Person'
        ELSE 'Others'
       END AS online
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY online
ORDER BY resolution_time DESC;
""").df()

avg_resolution_time_by_mode

# %%
avg_resolution_time_by_mode.merge(length_by_mode, how = 'left', on = 'mode')[['mode', 'resolution_time', 'length']]

# %% [markdown]
# ### Scatter plot

# %%
# Resolution time by mode
length_resolution_time = cur.execute(f"""
SELECT  ticket_no,
        DATEDIFF('day', created_on, resolved_on) AS resolution_time,
        LEN(grievance) as length,
        CASE 
            WHEN mode == 'Mobile' OR mode == 'Whatsapp' OR mode == 'Website' THEN 'Online'
            WHEN mode == 'CM Weekly Grievance' OR mode == 'Physical' OR mode == 'Joint Hearing' THEN 'In Person'
            ELSE 'Others'
        END AS online
FROM complaints
WHERE resolved_on IS NOT NULL
""").df()

length_resolution_time

# %% [markdown]
# ## WHY? Small characters

# %%
length_by_mode = cur.execute("""
    SELECT mode,
            CASE 
                WHEN mode == 'Mobile' OR mode == 'Whatsapp' OR mode == 'Website' THEN 'Online'
                WHEN mode == 'CM Weekly Grievance' OR mode == 'Physical' OR mode == 'Joint Hearing' THEN 'In Person'
                ELSE 'Others'
            END AS online, 
            ROUND(AVG(LEN(grievance)),0) as length,
            COUNT(*) as count
    FROM complaints
    WHERE resolved_on IS NOT NULL
    GROUP BY mode
    ORDER BY length DESC
    """).df()

length_by_mode['pct'] = round(length_by_mode['count'] / length_by_mode['count'].sum()*100,0)
length_by_mode

# %%


# %%
small_grievance_bymode = cur.execute("""
    SELECT  SUM((LEN(grievance)) > 400) as big, COUNT(*) AS count
    FROM complaints
    ORDER BY big DESC
    """).df()

small_grievance_bymode['pct'] = round(small_grievance_bymode['big']/small_grievance_bymode['count']*100,1)
small_grievance_bymode

# %%
# EXAMPLES
cur.execute("""
    SELECT DISTINCT grievance, mode, COUNT(*) as count
    FROM complaints
    WHERE LEN(grievance) < 25
    GROUP BY grievance, mode
    ORDER BY count DESC
    LIMIT 50
""").df()


# %%
with_docs_by_small = cur.execute("""
SELECT (LEN(grievance) < 25) as small, SUM(document_url IS NOT NULL AND document_url != '') as documents, COUNT(*) as count
FROM complaints
GROUP BY small
""").df()

with_docs_by_small['pct'] = round(with_docs_by_small['documents']/with_docs_by_small['count'] * 100, 0)
with_docs_by_small

# %%
cur.execute("""
SELECT AVG(LENGTH(grievance)) as avg_length, mode
FROM complaints
GROUP BY mode
            """).df()

# %%
resolution_time_by_small = cur.execute("""
SELECT (LEN(grievance) < 25) as small, 
        ROUND(AVG(DATEDIFF('day', created_on, resolved_on)), 1) AS resolution_time,
        ROUND(MEDIAN(DATEDIFF('day', created_on, resolved_on)), 1) AS median
FROM complaints
WHERE office != 'Collector'
GROUP BY small
""").df()

resolution_time_by_small

# %%
resolution_time_by_small = cur.execute("""
SELECT (LEN(grievance) > 400) as big, 
        ROUND(AVG(DATEDIFF('day', created_on, resolved_on)), 1) AS resolution_time,
        ROUND(MEDIAN(DATEDIFF('day', created_on, resolved_on)), 1) AS median,
FROM complaints
WHERE mode == 'Website' OR mode == 'Whatsapp' OR mode == 'Mobile'
GROUP BY big 
ORDER BY big ASC 
""").df()

resolution_time_by_small

# %%


# %%
open_by_small = cur.execute("""
SELECT (LEN(grievance) < 25) as small, SUM(resolved_on IS NOT NULL) as resolved, COUNT(*) as count
FROM complaints
GROUP BY small
""").df()

open_by_small['pct'] = round(open_by_small['resolved']/open_by_small['count'] * 100, 0)
open_by_small

# %%
#Avg and median time by large/small grievance AND avg and median number of steps 
cur.execute("CREATE TABLE action_steps AS SELECT * FROM avg_steps")


# %%
time_and_steps_by_lenght = cur.execute("""
SELECT (LEN(c.grievance) > 400) as big, 
        ROUND(AVG(DATEDIFF('day', c.created_on, c.resolved_on)), 1) AS resolution_time,
        ROUND(MEDIAN(DATEDIFF('day', c.created_on, c.resolved_on)), 1) AS median,
        AVG(count) as avg_steps
FROM complaints as c
JOIN action_steps as a ON a.ticket_no == c.ticket_no
WHERE mode == 'Whatsapp' OR mode == 'Mobile' OR mode == 'Website'
GROUP BY big
ORDER BY big ASC
""").df()

time_and_steps_by_lenght

# %% [markdown]
# # OTHERS

# %% [markdown]
# ### Times (by category)
# % open grievances with +30 days over all open grievances
# % grievances with +30 days that use reminders -> go to the impact

# %%
#Resolution time vs. Default (30 days)
avg_resolution_time['more_than_60'] = (avg_resolution_time['resolution_time'] > 60)
avg_resolution_time

# %% [markdown]
# #### % complaints resolved in more than 30 days

# %%
grievance_more_30_days = cur.execute(f"""
SELECT SUM((DATEDIFF('second', created_on, resolved_on)/86400) > 30) AS grievance_more_30days, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL
""").df()


# %%
grievance_more_30_days['pct_more_30_days'] = round(grievance_more_30_days['grievance_more_30days'] / grievance_more_30_days['count'] * 100, 2)
grievance_more_30_days

# %% [markdown]
# ### Video

# %%
cur.execute(f"""
SELECT category, dept, COUNT(*) as count
FROM complaints
WHERE grievance LIKE '%pension%'
GROUP BY category, dept
""").df()

# %%
grievance_more_30_days_by_cat = cur.execute(f"""
SELECT category, SUM((DATEDIFF('second', created_on, resolved_on)/86400) > 30) AS grievance_more_30days, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL
GROUP BY category
ORDER BY grievance_more_30days DESC;
""").df()


# %%
grievance_more_30_days_by_cat['pct_more_30_days'] = round(grievance_more_30_days_by_cat['grievance_more_30days'] / grievance_more_30_days_by_cat['count'] * 100, 2)
grievance_more_30_days_by_cat

# %% [markdown]
# ### % open grievances that have more than 30 days

# %%
open_grievance = cur.execute(f"""
SELECT subcategory, AVG(DATEDIFF('day', created_on, TIMESTAMP '2025-06-16 00:00:00')) AS pending_days, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NULL
GROUP BY subcategory
ORDER BY count DESC
""").df()

open_grievance

# %%
open_grievance = cur.execute(f"""
SELECT subcategory, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NULL
GROUP BY subcategory
""").df()
open_grievance

# %%
open_grievance_by_category = cur.execute(f"""
SELECT category, SUM(DATEDIFF('day', created_on, TIMESTAMP '2025-06-16 00:00:00') > 30) AS grievance_more_30days, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NULL
GROUP BY category
ORDER BY grievance_more_30days DESC
""").df()

open_grievance_by_category['pct_more_30_days'] = round(open_grievance_by_category['grievance_more_30days'] / open_grievance_by_category['count'] * 100, 2)
open_grievance_by_category

# %% [markdown]
# ### Grievances under miscelaneous and general

# %%
table = top10.merge(avg_resolution_time, how='left', on='category')
table[table['category'].isin(['General','Miscellaneous'])]

# %%
grievance_more_30_days_by_cat[grievance_more_30_days_by_cat['category'].isin(['General','Miscellaneous'])]

# %% [markdown]
# ### % Grievances with small text information

# %%
small_grievance = cur.execute("""
    SELECT SUM((LEN(grievance)) < 30) as small, COUNT(*) AS count
    FROM complaints
    """).df()

small_grievance['pct'] = round(small_grievance['small']/small_grievance['count']*100,2)
small_grievance

# %%
small_grievance_bymode = cur.execute("""
    SELECT mode, SUM((LEN(grievance)) < 30) as small, COUNT(*) AS count
    FROM complaints
    GROUP BY mode
    ORDER BY small DESC
    """).df()

small_grievance_bymode['pct'] = round(small_grievance_bymode['small']/small_grievance_bymode['count']*100,2)
small_grievance_bymode

# %%
small_grievance = cur.execute("""
    SELECT category, SUM((LEN(grievance)) < 30) as small, COUNT(*) AS count
    FROM complaints
    GROUP BY category
    ORDER BY small DESC
    """).df()

small_grievance['pct'] = round(small_grievance['small']/small_grievance['count']*100,2)
small_grievance

# %% [markdown]
# ### % grievances with document attached

# %%
complaints_with_docs = cur.execute("""
SELECT SUM(document_url IS NOT NULL AND document_url != '') as documents, COUNT(*) as count
FROM complaints
""").df()

complaints_with_docs['pct'] = round(complaints_with_docs['documents']/complaints_with_docs['count']*100,2)
complaints_with_docs

# %%
complaints_with_docs_by_mode = cur.execute("""
SELECT mode, SUM(document_url IS NOT NULL AND document_url != '') as documents, COUNT(*) as count
FROM complaints
GROUP BY mode,
ORDER BY count DESC
""").df()

complaints_with_docs_by_mode['pct'] = round(complaints_with_docs_by_mode['documents']/complaints_with_docs_by_mode['count']*100,2)
complaints_with_docs_by_mode

# %% [markdown]
# ### % of grievance that exceed the 'average steps' in actions 

# %%
res = cur.execute(f"PRAGMA table_info(action_history)")
res.df()

# %%
reminders = cur.execute("""
SELECT DISTINCT ticket_no, (action_status == 'Reminder Sent') as reminder
FROM action_history
""").df()

reminders.groupby('reminder')['reminder'].count()

# %%
query = """
SELECT ticket_no, COUNT(*) as count
FROM action_history
GROUP BY ticket_no
"""

avg_steps = cur.execute(query).df()

# %%
avg_steps

# %%
avg_steps['count'].mean()

# %%


# %% [markdown]
# ### % of Odia grievances

# %%
query = """
WITH cleaned AS (
  SELECT
    ticket_no,
    category,
    mode,
    REGEXP_REPLACE(
      grievance,
      '[^A-Za-z\\x{0900}-\\x{097F}\\x{0B00}-\\x{0B7F}]',
      '',
      'g'
    ) AS letters
  FROM complaints
  WHERE grievance IS NOT NULL
),
languages AS (
    SELECT  ticket_no,
            letters, 
            LENGTH(letters) AS total,
            total - LENGTH(REGEXP_REPLACE(letters, '[\\x{0B00}-\\x{0B7F}]', '', 'g')) AS num_odia, 
            total - LENGTH(REGEXP_REPLACE(letters, '[\\x{0900}-\\x{097F}]', '', 'g')) AS num_hi, 
            total - LENGTH(REGEXP_REPLACE(letters, '[A-Za-z]', '', 'g')) AS num_eng,
            ROUND(num_eng/total*100, 1) AS pct_eng,
            ROUND(num_odia/total*100, 1) AS pct_odia,
            ROUND(num_hi/total*100, 1) AS pct_hindi
    FROM cleaned
)
SELECT SUM(pct_eng > 70) AS most_eng, SUM(pct_odia > 70) AS most_odia, COUNT(*) as total
FROM languages; 
"""

english = cur.execute(query).df()

# %%
english['pct_eng'] = round(english['most_eng']/english['total']*100,1)
english['pct_odia'] = round(english['most_odia']/english['total']*100,1)
english

# %% [markdown]
# ## HOURS

# %%
query = """
SELECT
    COUNT(*) as count,
    strftime(created_on, '%A') AS weekday_name
FROM complaints

"""
cur.execute(query).df()

# %% [markdown]
# ## Description of the action taken report

# %%
cur.execute("""
SELECT action_taken_remark, COUNT(*) as count
from action_history
WHERE action_status == 'Open'
GROUP BY action_taken_remark
""").df()

# %%
query = """
WITH time_to_assing AS (
WITH ranked AS (
    SELECT
        ticket_no,
        action_taken_date,
        ROW_NUMBER() OVER (PARTITION BY ticket_no ORDER BY action_taken_date) AS rn
    FROM action_history
)
SELECT
    r1.ticket_no,
    DATEDIFF('day', r1.action_taken_date, r2.action_taken_date) AS diff
FROM ranked r1
JOIN ranked r2
  ON r1.ticket_no = r2.ticket_no
 AND r1.rn = 1
 AND r2.rn = 2
)
SELECT (LEN(c.grievance) > 400) as big, 
        ROUND(AVG(DATEDIFF('day', c.created_on, c.resolved_on)), 1) AS resolution_time,
        ROUND(MEDIAN(DATEDIFF('day', c.created_on, c.resolved_on)), 1) AS median,
        ROUND(AVG(diff),1) as time_to_assing
FROM complaints as c
JOIN time_to_assing as tta ON tta.ticket_no == c.ticket_no
WHERE c.mode == 'Website' OR c.mode == 'Whatsapp' OR c.mode == 'Mobile'
GROUP BY big
ORDER BY big DESC
"""

time_to_assing = cur.execute(query).df()
time_to_assing

# %%
cur.execute("""
SELECT DISTINCT action_status, COUNT(*) as count
FROM action_history
GROUP BY action_status
ORDER BY count
""").df()

# %%
misrouting = cur.execute("""
SELECT ticket_no, action_taken_remark, action_status
from action_history
WHERE action_taken_remark LIKE '%wrongly assigned%'
    OR action_taken_remark LIKE '%wrongly marked%'
    OR action_taken_remark LIKE '%wrongly sent%'
    OR action_taken_remark LIKE '%other department%'
    OR action_taken_remark LIKE '%relates to%'
    OR action_taken_remark LIKE '%not under%'
            
""").df()

misrouting

# %% [markdown]
# # GRAPHS AND MAPS

# %%
import altair as alt
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go


block_shp = gpd.read_file(Path('C:/Users/canun/OneDrive - The University of Chicago/2. Trabajo/DPIC/Odisha Shapefile/Odisha_Admin_Block_BND_2021.shp'))


# %% [markdown]
# ## Fuzzy match district and block names 

# %%
query = """
SELECT DISTINCT district, block  
FROM complaints
WHERE block IS NOT NULL
"""
blocks_2 = cur.execute(query).df()

# %%
blocks_2.loc[blocks_2['block'] == 'Banki- dampada','block'] = 'Dampada'
blocks_2.loc[blocks_2['block'] == 'Bamra','block'] = 'Govindapur'

blocks_2

# %%
set_db = list(blocks_2['district'].unique())

# %%
set_shp = list(block_shp['district_n'].unique())

# %%
from jellyfish import jaro_winkler_similarity

mapping_dist = {}
for dist1 in set_db:
    max_sim = 0
    map_dist = None
    for dist2 in set_shp:
        sim = jaro_winkler_similarity(dist1, dist2)
        if sim > max_sim:
            max_sim = sim
            map_dist = dist2
    mapping_dist[dist1] = map_dist

mapping_dist['Subarnapur'] = 'Sonepur'

mapping_blocks = {}
for dist1 in set_db:
    blocks_db = blocks_2['block'][blocks_2['district'] == dist1]
    blocks_shp = block_shp['block_name'][block_shp['district_n'] == mapping_dist[dist1]]
    dic_map_block = {}

    for block1 in blocks_db:
        max_sim = 0
        map_block = None
        for block2 in blocks_shp:
            sim = jaro_winkler_similarity(block1, block2)
            if sim > max_sim:
                max_sim = sim
                map_block = block2
        dic_map_block[block1] = map_block
    mapping_blocks[dist1] = dic_map_block

# %%
rows = [(old, new) for old, new in mapping_dist.items() if new is not None]
dist_df = pd.DataFrame(rows, columns=["district_old", "district_new"]).drop_duplicates()
dist_df

# %%
rows = []
for dist_old, bmap in mapping_blocks.items():
    for block_old, block_new in bmap.items():
        if block_new is not None:
            rows.append((dist_old, block_old, block_new))

block_df = pd.DataFrame(rows, columns=["district_old","block_old","block_new"]).drop_duplicates()



# %%
block_df = block_df.merge(dist_df, how = 'left', on = 'district_old')

# %% [markdown]
# ## Maps

# %% [markdown]
# ### Queries for number of complaints and resolution time

# %%
# Resolution time by block

query = """
SELECT district, block, SUM(DATEDIFF('day', created_on, resolved_on)) AS sum_resolution_time, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL AND block IS NOT NULL
GROUP BY district, block
;
"""

block_resolution_time = cur.execute(query).df()

# Nature of the grievance subcategories

# %%
block_times = block_resolution_time.merge(block_df, how = 'left', left_on=['district', 'block'], right_on =['district_old', 'block_old'])[['district', 'block','district_new', 'block_new', 'sum_resolution_time', 'count']]

# %%
block_times

# %%
block_times_df = block_times[['district_new', 'block_new', 'sum_resolution_time', 'count']].groupby(['district_new', 'block_new'])[['sum_resolution_time', 'count']].sum().reset_index()

block_times_df['avg_time'] = block_times_df['sum_resolution_time']/block_times_df['count']

# %%
block_times_df

# %%
block_shp = block_shp.merge(block_times_df, how='left', left_on=['district_n','block_name'], right_on=['district_new','block_new'])

# %%
block_shp[['block_name','district_n', 'district_new', 'block_new']]

# %%
block_times_df

# %%
dist_times_df = block_times[['district_new', 'block_new', 'sum_resolution_time', 'count']].groupby(['district_new'])[['sum_resolution_time', 'count']].sum().reset_index()
dist_times_df['avg_time'] = dist_times_df['sum_resolution_time']/dist_times_df['count']

# %%
dist_times_df

# %% [markdown]
# ### District map for number of complaints

# %%
# Importing shapefile 
district_shp = gpd.read_file(Path('C:/Users/canun/OneDrive - The University of Chicago/2. Trabajo/DPIC/Odisha Shapefile/Odisha_Admin_District_BND_2021.shp'))

# %%
# Importing population data
dist_pop = pd.read_csv('data/raw/pop2011.csv', delimiter=";")[['district_n','pop']]

# %%
# Normalizing district names before merge
dist_pop = dist_pop.merge(dist_df, how = 'left', left_on='district_n', right_on='district_old')
dist_pop = dist_pop[['district_n', 'pop', 'district_new']]

# %%
# Merge geopandas with complaints data
district_shp = district_shp.merge(dist_times_df, how='left', left_on='district_n', right_on='district_new')
district_shp = district_shp[['district_n', 'district_c', 'state_name', 'state_code', 'geometry', 'sum_resolution_time', 'count', 'avg_time']]

# Merging geopandas district data with population data
district_data = district_shp.merge(dist_pop, how = 'left', left_on = 'district_n', right_on = 'district_new')
district_data = district_data[['district_n_x', 'geometry', 'sum_resolution_time', 'count', 'avg_time', 'pop']]
district_data = district_data.rename(columns={'district_n_x':'district_n',
                                              'count': 'n_complaints'})

# %%
# Normalizing complaints count
district_data['complaints_per_1000hab'] = round(district_data['n_complaints'] / district_data['pop'] * 1000, 0)

# %%
import numpy as np

# Compute tertile cut points
district_data = district_data.copy()

# Define fixed bins and labels
bins = [0, 5000, 15000, np.inf]  # upper limits
labels = ["<5,000", "5,000–15,000", "15,000+"]

# Categorize based on fixed ranges
district_data['n_complaints_cat'] = pd.cut(
    district_data['n_complaints'],
    bins=bins,
    labels=labels,
    right=False  # includes lower bound, excludes upper bound
)

# Optional custom colors (light → dark blue)
cat_colors = ["#e4f5bd", "#49afbf", "#263184"]

# %%
complaints_map = alt.Chart(district_data).mark_geoshape(
    stroke='black', strokeWidth=0.5
).encode(
    color=alt.Color(
        'n_complaints_cat:N',
        title='Number of complaints',
        scale=alt.Scale(domain=labels, range=cat_colors),
        legend=alt.Legend(title='Number of complaints ranges')
    ),
    tooltip=[
        alt.Tooltip('district_n:N', title='District'),
        alt.Tooltip('n_complaints:Q', title='Number of complaints', format='.0f'),
        alt.Tooltip('n_complaints_cat:N', title='Range')
    ]
).properties(width=1000, height=600).project(type='identity', reflectY=True)

complaints_map

# %%
complaints_per_1000hab = alt.Chart(district_data).mark_geoshape(stroke='black', strokeWidth=0.5
).encode(
    color = alt.Color('n_complaints', 
                      type="quantitative", 
                      title="Complaints"),
    tooltip = [alt.Tooltip("district_n", title = "District"),
               alt.Tooltip("n_complaints", title = 'Number of complaints', format='.0f')]
).properties(
    width=1000,
    height=600,
).project(
    type = 'identity',
    reflectY=True
    )
complaints_per_1000hab

# %%
import numpy as np

# Compute tertile cut points
district_data = district_data.copy()

# Define fixed bins and labels
bins = [30, 60, 90, np.inf]  # upper limits
labels = ["30–60", "60–90", "90+"]

# Categorize based on fixed ranges
district_data['avg_time_cat'] = pd.cut(
    district_data['avg_time'],
    bins=bins,
    labels=labels,
    right=False  # includes lower bound, excludes upper bound
)

# Optional custom colors (light → dark blue)
cat_colors = ["#e4f5bd", "#49afbf", "#263184"]

# %%
avg_time = alt.Chart(district_data).mark_geoshape(
    stroke='black', strokeWidth=0.5
).encode(
    color=alt.Color(
        'avg_time_cat:N',
        title='Average resolution time (days)',
        scale=alt.Scale(domain=labels, range=cat_colors),
        legend=alt.Legend(title='Time ranges (in days)')
    ),
    tooltip=[
        alt.Tooltip('district_n:N', title='District'),
        alt.Tooltip('avg_time:Q', title='Average resolution time (days)', format='.0f'),
        alt.Tooltip('avg_time_cat:N', title='Range')
    ]
).properties(width=1000, height=600).project(type='identity', reflectY=True)

avg_time

# %%
avg_time = alt.Chart(district_data).mark_geoshape(stroke='white', strokeWidth=0.5
).encode(
    color = alt.Color('avg_time:Q', 
                      type="quantitative", 
                      title="Average resolution time (in days)",
                      scale=alt.Scale(
                          type='quantile',
                          scheme=alt.SchemeParams(name='blues', count=4))),
    tooltip = [alt.Tooltip("district_n", title = "District"),
               alt.Tooltip("avg_time", title = 'Average resolution time (in days)', format='.0f')]
).properties(
    width=1000,
    height=600,
).project(
    type = 'identity',
    reflectY=True
    )
avg_time

# %%
variable_list = ['n_complaints', 'avg_time']

base = (
    alt.Chart(district_data)
      .properties(width=500, height=300)
      .project(type='identity', reflectY=True)
)

chart = (
    base.mark_geoshape(stroke='white', strokeWidth=0.5)
        .encode(
            color=alt.Color(
                alt.repeat('row'), type='quantitative'
            ),
            tooltip=[
                alt.Tooltip('district_n:N', title='District'),
                alt.Tooltip(alt.repeat('row'), type='quantitative', format='.0f')
            ]
        )
        .repeat(row=variable_list)          # e.g., ['count_x','avg_time',...]
        .resolve_scale(color='independent') # per-panel bins/legend
)

chart

# %% [markdown]
# ### Case Study: Rural Housing and PMAY

# %%
rural_housing = cur.execute("""
SELECT district, COUNT(*) as count
FROM complaints
WHERE subcategory == 'Rural Housing' OR subcategory == 'IAY/MKY/BPGY/PMAY'
GROUP BY district
ORDER BY count DESC
""").df()

rural_housing['pct'] = round(rural_housing['count'] / rural_housing['count'].sum() * 100,0)
rural_housing

# %% [markdown]
# ### Case Study: Ganjam

# %%
map_block = block_shp[block_shp['district_n'] == 'Ganjam']
map_block = map_block[['block_name', 'district_n', 'geometry', 'sum_resolution_time', 'count', 'avg_time']]
map_block = map_block.rename(columns={'count':'n_complaints'})

# %%
pop_ganjam = dict(zip(['Aska', 'Bellaguntha', 'Bhanjanagar', 'Buguda', 'Chhatrapur',
       'Chiketi', 'Dharakote', 'Digapahandi', 'Ganjam', 'Hinjilicut',
       'Jagannathprasad', 'Kabisuryanagar', 'Khallikote',
       'Kodala(Beguniapada)', 'Kukudakhandi', 'Patrapur', 'Polasara',
       'Purusottampur', 'Rangeilunda', 'Sanakhemundi', 'Sheragada',
       'Sorada'],
       [144132, 113436, 138774, 114272, 135751,
        104572, 107946, 148484, 89170, 109877,
        131326, 114354, 169171, 
        134093, 147313, 128711, 133386,
        143156, 161372, 163138, 127807,
        133386
        ]))

pop_deogarh = dict(zip(
    [],
    []
))

map_block['population'] = map_block['block_name'].map(pop_ganjam)

# %%
map_block['complaints_per_1000hab'] = round(map_block['n_complaints'] / map_block['population'] * 1000, 0)

# %%
# Compute tertile cut points
map_block = map_block.copy()

# Define fixed bins and labels
bins = [0, 500, 1000, 2500, np.inf]  # upper limits
labels = ["<500", "500–1,000", "1,000–2,500", "2,500+"]

# Categorize based on fixed ranges
map_block['n_complaints_cat'] = pd.cut(
    map_block['n_complaints'],
    bins=bins,
    labels=labels,
    right=False  # includes lower bound, excludes upper bound
)

# Optional custom colors (light → dark blue)
cat_colors = ["#e4f5bd", "#97d2be", "#49afbf", "#263184"]

# %%
complaints_ganjam = alt.Chart(map_block).mark_geoshape(
    stroke='black', strokeWidth=0.5
).encode(
    color=alt.Color(
        'n_complaints_cat:N',
        title='Number of complaints',
        scale=alt.Scale(domain=labels, range=cat_colors),
        legend=alt.Legend(title='Number of complaints ranges')
    ),
    tooltip=[
        alt.Tooltip('district_n:N', title='District'),
        alt.Tooltip('n_complaints:Q', title='Number of complaints', format='.0f'),
        alt.Tooltip('n_complaints_cat:N', title='Range')
    ]
).properties(width=1000, height=600).project(type='identity', reflectY=True)

complaints_ganjam

# %%
blocks = alt.Chart(map_block).mark_geoshape(stroke='black', strokeWidth=0.5
    ).encode(
    color = alt.Color('n_complaints', type="quantitative", title="Number of complaints"),
    tooltip = [alt.Tooltip("district_n", title = "District"),
               alt.Tooltip("block_name", title = "Block"),
               alt.Tooltip("n_complaints", title = "Complaints")]
).properties(
    width=1000,
    height=600,
).project(
    type = 'identity',
    reflectY=True
    )
blocks

# %%
# Compute tertile cut points
map_block = map_block.copy()

# Define fixed bins and labels
bins = [20, 30, 40, 50, np.inf]  # upper limits
labels = ["20-30", "30–40", "40–50", "50+"]

# Categorize based on fixed ranges
map_block['avg_time_cat'] = pd.cut(
    map_block['avg_time'],
    bins=bins,
    labels=labels,
    right=False  # includes lower bound, excludes upper bound
)

# Optional custom colors (light → dark blue)
cat_colors = ["#e4f5bd", "#97d2be", "#49afbf", "#263184"]

# %%
avg_time = alt.Chart(map_block).mark_geoshape(
    stroke='black', strokeWidth=0.5
).encode(
    color=alt.Color(
        'avg_time_cat:N',
        title='Average resolution time (days)',
        scale=alt.Scale(domain=labels, range=cat_colors),
        legend=alt.Legend(title='Time ranges (in days)')
    ),
    tooltip=[
        alt.Tooltip('district_n:N', title='District'),
        alt.Tooltip('avg_time:Q', title='Average resolution time (days)', format='.0f'),
        alt.Tooltip('avg_time_cat:N', title='Range')
    ]
).properties(width=1000, height=600).project(type='identity', reflectY=True)

avg_time

# %%
blocks = alt.Chart(map_block).mark_geoshape(stroke='black', strokeWidth=0.5
).encode(
    color = alt.Color('avg_time', 
                      type="quantitative", 
                      title="Average resolution time (in days)"),
    tooltip = [alt.Tooltip("district_n", title = "District"),
               alt.Tooltip("avg_time", title = 'Average resolution time (in days)', format='.0f')]
).properties(
    width=1000,
    height=600,
).project(
    type = 'identity',
    reflectY=True
    )

blocks

# %%
# Resolution time by block

query = """
SELECT district, block, category, subcategory, COUNT(*) as count
FROM complaints
WHERE resolved_on IS NOT NULL AND block IS NOT NULL
GROUP BY district, block, category, subcategory;
"""

block_categories = cur.execute(query).df()

# %%
block_categories_df = block_categories.merge(block_df, how = 'left', left_on=['district', 'block'], right_on =['district_old', 'block_old'])[['district', 'block','district_new', 'block_new', 'category', 'subcategory', 'count']]


# %%
ganjam = block_categories_df[block_categories_df['district_new'] == 'Ganjam']
ganjam_by_subcat = ganjam.groupby(['district_new','category','subcategory'])['count'].sum().reset_index()

ganjam_by_subcat['pct'] = round(ganjam_by_subcat['count'] / ganjam_by_subcat['count'].sum()*100,0)
ganjam_by_subcat

# %% [markdown]
# # PYTESSERACT OCR

# %%
from pdf2image import convert_from_path
import pytesseract
import re

# %%
def extracting_ocr_text(pdf_path: str):
    """
    Extracts text from a PDF file containing graphs.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        str: The extracted text from the PDF file.
    """
    # Step 1: Convert the PDF pages to images
    pages = convert_from_path(pdf_path, dpi=500) # TODO EL CPI HACE QUE SE PIERDA INFORMACIÓN

    # Step 2: Extract text from images using pytesseract
    ocr_text1 = ""
    for _, page in enumerate(pages):
        ocr_text1 += pytesseract.image_to_string(page, lang='eng+ori')
        ocr_text1 = re.sub(r"\|", "I", ocr_text1)
    return ocr_text1

# %%
from pathlib import Path
import os

# %%
path = 'data/raw/documents'
doc = os.listdir('data/raw/documents')[0]
doc_path = path + '/' + doc
extracting_ocr_text(doc_path)

# %%
doc = os.listdir('data/raw/documents')[2]
doc_path = path + '/' + doc
ocr_text = extracting_ocr_text(doc_path)

# %%
print(ocr_text)

# %%
pytesseract.get_languages()

# %%
print(ocr_text)

# %%
print(ocr_text)

# %%
import pdfplumber

# %%
def extract_data_from_pdf(path_to_pdf: str) -> str:
    """
    Takes a PDF and returns all the text from it
    Input:
        - path to pdf: str
    Return:
        - text from pdf: str
    """
    with pdfplumber.open(path_to_pdf) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

# %%



