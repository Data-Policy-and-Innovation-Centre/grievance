# %% [markdown]
# ## 1. Loading Data

# %%
# Code for pulling Status 2:

# subset_complaints = []

# for dist_id in range(344, 374):
#     # for status_id in range(0,3):
#         for office_id in range(1,8):
#             try:
#                 print(f"Fetching complaints for district={dist_id}, status=1, office={office_id}")
#                 complaints = client.get_complaints(year=2025, distId=dist_id, status=2, office=office_id)
#                 validated = validate(complaints, Complaint)
#                 subset_complaints.extend(validated)

#             except JanasunaniAPIError as e:
#                 print(f"Custom error occurred: {e}")

# df_subset_complaints = pd.DataFrame(subset_complaints)

# %%
from pathlib import Path
import pandas as pd
from app.ingestion.client import JanasunaniAPIClient
from app.ingestion.schemas import validate, District, Complaint, validate_action_history
#from skimpy import skim
from app.ingestion.client import JanasunaniAPIError
import pandas as pd

client = JanasunaniAPIClient()
# Change the path to the directory where your JSON files are located

df_complaints = pd.DataFrame()

for status in range(0,3):
    df_status = pd.read_json(f'data/raw/grievances2025_{status}.json')
    if status == 0:
        df_status.columns = ['ticket_no', 'petitioner_name', 'petitioner_mobile', 'petitioner_email',
       'grievance', 'office', 'received_by', 'district', 'block', 'address',
       'mode', 'disability', 'status', 'govt_ticket', 'created_on',
       'tagged_to', 'tagged_by', 'tagged_date', 'category', 'dept',
       'subcategory', 'state', 'petitioner_gender', 'transfer_status',
       'urgent']
    if status in (1, 2):
        # Convert all date columns from string to datetime (auto-detect format)
        date_cols = ['created_on', 'tagged_date', 'assigned_on', 'escalation_date', 'resolved_on']

        for col in date_cols:
            if col in df_status.columns:
                df_status[col] = pd.to_datetime(df_status[col], unit='ms')

    df_status['status_id'] = status
    df_complaints = pd.concat([df_complaints, df_status], ignore_index=True)
    
df_complaints

# %%
df_complaints['ticket_no'].value_counts()

# %%
#client.get_action_history("DM20251122747")

# %%
# Sort by ticket_no and then by the date priority
df_complaints_sorted = df_complaints.sort_values(by=['ticket_no', 'created_on', 'escalation_date', 'resolved_on'])

# Keep the first occurrence of each ticket_no - remove duplicates
df_unique = df_complaints_sorted.drop_duplicates(subset='ticket_no', keep='first')

# %%
len(df_unique) # should have 158010 unique complaints in 2025 across all statuses

# %%
df_unique['office'] = df_unique['office'].str.replace('Supertendent of Police', 'Superintendent of Police', regex=False) # standardize naming

# %%
df_unique.status_id.value_counts(normalize=True).mul(100).round(2)

# %%
df_unique['district'].value_counts(normalize=True)*100

# %% [markdown]
# ## 2. Understanding Different Categories, Modes, Offices

# %% [markdown]
# #### 2.1. Category Overview

# %%
df_unique.category.value_counts(normalize=True).mul(100).round(1)

# %%
df_unique['category'] = df_unique['category'].replace(
    {'General': 'General & Misc', 'Miscellaneous': 'General & Misc'} # group the 2 into 1 category 
)
df_unique.category.value_counts(normalize=True).mul(100).round(1)


# %%
df_unique[df_unique['category']=='Social Welfare']['dept'].value_counts().head() # look at the departments under Social Welfare


# %%
def assign_category(text): # broadly categorize the content in grievance text 
    housing_keys = ['pmay', 'pmagy', 'housing', 'awas', 'yojana', 'yojna', 'house']
    if any(key in text for key in housing_keys):
        return 'Housing'
    elif 'subhadra' in text:
        return 'Subhadra Scheme'
    elif 'ration card' in text:
        return 'Ration Card'
    else:
        return 'Other'

df_unique['grievance_category'] = df_unique['grievance'].str.lower().apply(assign_category)

def is_mostly_ascii(text, threshold=0.9): # filter out mostly english grievances 
    if not isinstance(text, str):
        return False
    ascii_chars = sum(c.isascii() for c in text)
    return ascii_chars / len(text) >= threshold

df_english = df_unique[df_unique['grievance'].apply(is_mostly_ascii)]

# Analyze complaints tagged to Social Welfare and Panchayati Raj & Drinking Water and look for misclassifications
count = df_english[(df_english['category']=='Social Welfare') & (df_english['dept']=='Panchayati Raj & Drinking Water')]['grievance_category'].value_counts()
percent = df_english[(df_english['category']=='Social Welfare') & (df_english['dept']=='Panchayati Raj & Drinking Water')]['grievance_category'].value_counts(normalize=True).mul(100).round(1)

summary = pd.DataFrame({'count': count, 'percent': percent})
summary

# %%
# Analyzing Others Category
df_english[(df_english['category']=='Social Welfare') & (df_english['dept']=='Panchayati Raj & Drinking Water')&(df_english['grievance_category']=='Other')]['grievance']

# %% [markdown]
# #### 2.2. Mode Overview

# %%
df_unique['mode'].value_counts(normalize=True).mul(100).round(1)

# %% [markdown]
# #### 2.3. Office Overview

# %%
df_unique['office'].value_counts(normalize=True).mul(100).round(1)

# %% [markdown]
# #### 2.4. Mode and Office Overview

# %%
props = (
    df_unique
    .groupby('office')['mode']
    .value_counts(normalize=True)
    .mul(100)
    .round(1)
    .rename('percent')
    .reset_index()
)

# Step 2: Pivot to wide format — one row per office
office_mode_pct = props.pivot(index='office', columns='mode', values='percent').fillna(0)


office_mode_pct.reset_index()

# %% [markdown]
# ## 3. Understanding Different Statuses

# %%
# Getting high level overview of all the statuses across all offices 

import pandas as pd

df_counts = df_unique.groupby(['office', 'status_id']).size().reset_index(name='count')
office_totals = df_counts.groupby('office')['count'].sum().reset_index(name='total_complaints')
df_counts = df_counts.merge(office_totals, on='office')
df_counts['percentage'] = (df_counts['count'] / df_counts['total_complaints']) * 100
df_counts['percentage'] = df_counts['percentage'].round(1)

df_pivot = df_counts.pivot(index='office', columns='status_id', values=['count', 'percentage'])
df_pivot.columns = [f"count_statusid_{status}" if stat == 'count' else f"perc_statusid_{status}" for stat, status in df_pivot.columns]
df_pivot = df_pivot.reset_index()

df_summary = office_totals.merge(df_pivot, on='office')
df_summary.columns = ['office', 'total_complaints', 'count_unassigned',  'count_pending','count_disposed', 'perc_unassigned','perc_pending', 'perc_disposed']

df_summary

# %%
df_status0 = df_unique[df_unique["status_id"] == 0]
df_status1 = df_unique[df_unique["status_id"] == 1]
df_status2 = df_unique[df_unique["status_id"] == 2]

# %% [markdown]
# ### 3.1. Status 2 - Disposed Complaints

# %%
df_status2['benefitted'].value_counts(normalize=True).mul(100).round(1)

# %% [markdown]
# #### Share of Benefitted Across Offices, Departments and Modes

# %%
## Calculating Days to Resolve Across Benefitted and Not Benefitted

df_status2['created_on'] = pd.to_datetime(df_status2['created_on'], errors='coerce')
df_status2['days_to_dispose'] = (df_status2['resolved_on'] - df_status2['created_on']).dt.days
df_status2[['ticket_no','grievance','created_on', 'resolved_on', 'benefitted','days_to_dispose']]
avg_days_per_benefit_status = df_status2.groupby('benefitted')['days_to_dispose'].mean().reset_index()
avg_days_per_benefit_status.round(2)

# %%
df_status2['days_to_dispose'].mean()

# %%
# Calculating Averages Across Offices for Disposal
office_avg = df_status2.groupby('office')['days_to_dispose'].mean().round(0).reset_index()
office_avg = office_avg.rename(columns={'days_to_dispose': 'avg_days_to_dispose'})
office_avg = office_avg.sort_values(by='avg_days_to_dispose')
office_avg

# %%
# Looking at Only Benefitted

df_benefitted = df_status2[df_status2['benefitted'] == 'Yes']
avg_days_per_office_benefitted = df_benefitted.groupby('office')['days_to_dispose'].mean().round(0).reset_index()
avg_days_per_office_benefitted = avg_days_per_office_benefitted.rename(columns={'days_to_dispose': 'avg_days_to_benefit'})
avg_days_per_office_benefitted = avg_days_per_office_benefitted.sort_values(by='avg_days_to_benefit')
avg_days_per_office_benefitted

# %%
df_status2['benefitted_bool'] = df_status2['benefitted'].map({'Yes': True, 'No': False})

office_summary = (
    df_status2
    .groupby('office')['benefitted_bool']
    .agg(
        total_complaints='count',
        disposed_and_benefitted='sum'
    )
    .reset_index()
)

office_summary['disposed_without_benefit'] = office_summary['total_complaints'] - office_summary['disposed_and_benefitted']

office_summary['percent_benefitted'] = (office_summary['disposed_and_benefitted'] / office_summary['total_complaints'] * 100).round(1)
office_summary['percent_not_benefitted'] = (office_summary['disposed_without_benefit'] / office_summary['total_complaints'] * 100).round(1)
office_summary = office_summary.sort_values(by='percent_benefitted', ascending=False)

office_summary


# %%
dept_summary = (
    df_status2
    .groupby('category')['benefitted_bool']
    .agg(
        total_complaints='count',
        disposed_and_benefitted='sum'
    )
    .reset_index()
)

# Step 2: Calculate not-benefitted count
dept_summary['disposed_without_benefit'] = dept_summary['total_complaints'] - dept_summary['disposed_and_benefitted']

# Step 3: Compute percentages (rounded to 1 decimal)
dept_summary['percent_benefitted'] = (dept_summary['disposed_and_benefitted'] / dept_summary['total_complaints'] * 100).round(1)
dept_summary['percent_not_benefitted'] = (dept_summary['disposed_without_benefit'] / dept_summary['total_complaints'] * 100).round(1)

# Step 4: Sort by percent_benefitted (or any other metric)
dept_summary = dept_summary.sort_values(by='percent_benefitted', ascending=False)

dept_summary

# %%
mode_summary = df_status2.groupby('mode').agg(
    total_complaints = ('mode', 'count'),
    benefitted_complaints= ('benefitted_bool', 'sum'))

mode_summary['percent_benefitted'] = ((mode_summary['benefitted_complaints'] / mode_summary['total_complaints']) * 100).round(1)
mode_summary = mode_summary.sort_values(by='percent_benefitted', ascending=False)
mode_summary

# %% [markdown]
# #### Final Summary for Disposed Complaints Across Offices

# %%
merged1 = pd.merge(office_summary, office_avg, on='office', how='outer')

# Step 2: Merge the result with avg_days_per_office_benefitted
final_merged = pd.merge(merged1, avg_days_per_office_benefitted, on='office', how='outer')

# Step 3: Fill missing values with 0
final_merged = final_merged.fillna(0)
final_merged.round(1)

# %% [markdown]
# ### 3.2. Analyzing Pending & Unassigned Complaints

# %%
fixed_yesterday = pd.Timestamp('2025-06-22').normalize()

# %%
df_status1['created_on'] = pd.to_datetime(df_status1['created_on'], errors='coerce')
df_status1['days_open_without_disposal'] = (fixed_yesterday- df_status1['created_on'].dt.normalize()).dt.days
days_open = df_status1.groupby('office')['days_open_without_disposal'].mean().reset_index()
# days_open.round(0)

# %%
df_status0['created_on'] = pd.to_datetime(df_status0['created_on'], errors='coerce')
df_status0['days_without_assignment'] = (fixed_yesterday - df_status0['created_on'].dt.normalize()).dt.days
days_open_0 = df_status0.groupby('office')['days_without_assignment'].mean().reset_index()
days_open_0

# %% [markdown]
# #### Response Times Across Offices

# %%
import pandas as pd
from functools import reduce

dfs = [office_avg, avg_days_per_office_benefitted, days_open, days_open_0]
def prefix_avg_cols(df, key='office'):
    # Rename all columns except the key by adding 'avg_' prefix
    new_cols = {col: f'avg_{col}' for col in df.columns if col != key}
    return df.rename(columns=new_cols)

dfs_prefixed = [prefix_avg_cols(df) for df in dfs]
df_merged = reduce(lambda left, right: pd.merge(left, right, on='office', how='left'), dfs_prefixed)
df_merged = df_merged.fillna(0).round(0)
df_merged

# %% [markdown]
# ## 4. Understanding Channels - Online, Offline and Freetext

# %%
# Modes: Online vs. Offline 

df_online = df_unique[df_unique['mode'].isin(['Website', 'Whatsapp', 'Mobile'])]
df_offline = df_unique[df_unique['mode'].isin(['Joint Hearing', 'Physical','CM Weekly Grievance'])]
df_freetext = df_unique[df_unique['mode'].isin(['Letter', 'Email'])]


# %% [markdown]
# #### Online Channel

# %%
import numpy as np
# Ensure dates are datetime type
df_online['created_on'] = pd.to_datetime(df_online['created_on'])
df_online['resolved_on'] = pd.to_datetime(df_online['resolved_on'])
today = fixed_yesterday.floor('D')

# Calculate days open: resolved – created, else today – created
df_online['days_open_online'] = np.where(
    df_online['resolved_on'].notna(),
    (df_online['resolved_on'] - df_online['created_on']).dt.days,
    (today - df_online['created_on']).dt.days
)
online_resolution = df_online.groupby('office')['days_open_online'].mean().reset_index()


# %%
# Filter only records where benefitted is True
df_benefitted_online = df_online[df_online['benefitted'] == "Yes"]

# Compute average response time per office for benefitted tickets
online_benefitted_avg = (
    df_benefitted_online
    .groupby('office', as_index=False)
    .agg(avg_days_to_benefit_online=('days_open_online', 'mean')).round(0)
)

online_benefitted_avg

# %%
office_counts = df_online['office'].value_counts()
office_percent = df_online['office'].value_counts(normalize=True).mul(100).round(1)

# ONLINE OFFICE SUMMARY
online_summary = pd.DataFrame({'count': office_counts, 'percent': office_percent})
online_summary

# %%
dept_counts = df_online['dept'].value_counts()
dept_percent = df_online['dept'].value_counts(normalize=True).mul(100).round(1)

# ONLINE DEPT SUMMARY
online_dept_summary = pd.DataFrame({'count': dept_counts, 'percent': dept_percent})
online_dept_summary

# %%
cat_count = df_online['category'].value_counts()
cat_percent = df_online['category'].value_counts(normalize=True).mul(100).round(1)

# ONLINE CATEGORY SUMMARY
online_cat_summary = pd.DataFrame({'count': cat_count, 'percent': cat_percent})
online_cat_summary

# %% [markdown]
# #### Offline Channel

# %%
# Ensure dates are datetime type
df_offline['created_on'] = pd.to_datetime(df_offline['created_on'])
df_offline['resolved_on'] = pd.to_datetime(df_offline['resolved_on'])

# Use today’s date floored to the day
today = fixed_yesterday.floor('D')

# Calculate days open: resolved – created, else today – created
df_offline['days_open_offline'] = np.where(
    df_offline['resolved_on'].notna(),
    (df_offline['resolved_on'] - df_offline['created_on']).dt.days,
    (today - df_offline['created_on']).dt.days
)
offline_resolution = df_offline.groupby('office')['days_open_offline'].mean().reset_index()


# %%
# Filter only records where benefitted is True
df_benefitted_offline = df_offline[df_offline['benefitted'] == "Yes"]

# Compute average response time per office for benefitted tickets
offline_benefitted_avg = (
    df_benefitted_offline
    .groupby('office', as_index=False)
    .agg(avg_days_to_benefit_offline=('days_open_offline', 'mean'))
)

offline_benefitted_avg

# %%
office_counts = df_offline['office'].value_counts()
office_percent = df_offline['office'].value_counts(normalize=True).mul(100).round(1)

# OFFLINE OFFICE SUMMARY
offline_summary = pd.DataFrame({'count': office_counts, 'percent': office_percent})
offline_summary

# %%
dept_counts = df_offline['dept'].value_counts()
dept_percent = df_offline['dept'].value_counts(normalize=True).mul(100).round(1)

# OFFLINE DEPT SUMMARY
offline_dept_summary = pd.DataFrame({'count': dept_counts, 'percent': dept_percent})
offline_dept_summary

# %%
cat_count = df_offline['category'].value_counts()
cat_percent = df_offline['category'].value_counts(normalize=True).mul(100).round(1)

# OFFLINE CATEGORY SUMMARY
offline_cat_summary = pd.DataFrame({'count': cat_count, 'percent': cat_percent})
offline_cat_summary

# %%
df_offline['category'].value_counts()

# %% [markdown]
# #### Freetext Channel

# %%
# Ensure dates are datetime type
df_freetext['created_on'] = pd.to_datetime(df_freetext['created_on'])
df_freetext['resolved_on'] = pd.to_datetime(df_freetext['resolved_on'])

# Use today’s date floored to the day
today = fixed_yesterday .floor('D')

# Calculate days open: resolved – created, else today – created
df_freetext['days_open_text'] = np.where(
    df_freetext['resolved_on'].notna(),
    (df_freetext['resolved_on'] - df_freetext['created_on']).dt.days,
    (today - df_freetext['created_on']).dt.days
)

text_resolution = df_freetext.groupby('office')['days_open_text'].mean().reset_index()

# %%
# Filter only records where benefitted is True
df_benefitted_text = df_freetext[df_freetext['benefitted'] == "Yes"]

# Compute average response time per office for benefitted tickets
text_benefitted_avg = (
    df_benefitted_text
    .groupby('office', as_index=False)
    .agg(avg_days_to_benefit_text=('days_open_text', 'mean'))
)

text_benefitted_avg

# %% [markdown]
# #### Overall Office and Channel Summary for Online Channel

# %%

dfs = [online_resolution, offline_resolution, text_resolution, online_benefitted_avg,offline_benefitted_avg, text_benefitted_avg]

# Merge all dataframes on 'office' using an inner join (keep only matching offices)
df_merged_resolution = reduce(lambda left, right: pd.merge(left, right, on='office', how='left'),
                   dfs)

df_merged_resolution.fillna(0).round(0)

# %% [markdown]
# #### Office and Modes

# %%
df_online['channel'] = 'online'
df_offline['channel'] = 'offline'
df_freetext['channel'] = 'freetext'

df_all = pd.concat([df_online, df_offline, df_freetext], ignore_index=True)
counts = pd.crosstab(df_all['office'], df_all['channel'])
percents = pd.crosstab(df_all['office'], df_all['channel'], normalize='index').mul(100).round(1)
office_summary = (
    counts
    .add_suffix('_count')
    .join(percents.add_suffix('_percent'))
    .reset_index()
)
office_summary

# %%
mode_pivot = (
    df_unique
    .groupby(['office', 'mode'])
    .size()
    .unstack(fill_value=0)
)

mode_percent = mode_pivot.div(mode_pivot.sum(axis=1), axis=0) * 100
mode_percent.round(1)


# %% [markdown]
# #### Benefitted Rates and Resolution Times Across Channels

# %%
def avg_benefitted_days(df, channel_name, days_col):
    # Filter benefitted tickets only
    benef = df[df['benefitted'] == 'Yes']
    # Calculate average days open
    avg_days_benefitted = benef[days_col].mean() if not benef.empty else np.nan
    avg_days_open = df[days_col].mean()
    return pd.DataFrame({
        'channel': [channel_name],
        'n_complaints': [len(df)],
        'n_benefitted': [len(benef)],
        'benefitted_rate': [round((len(benef) / len(df)) * 100, 1)],
        f'avg_days_benefitted': [round(avg_days_benefitted, 0)],
        f'avg_days_open': [round(avg_days_open, 0)]
    })

# Compute for each dataset and column
online_avg = avg_benefitted_days(df_online, 'online', 'days_open_online')
offline_avg = avg_benefitted_days(df_offline, 'offline', 'days_open_offline')
freetext_avg = avg_benefitted_days(df_freetext, 'freetext', 'days_open_text')

# Combine into a summary
days_summary = pd.concat([online_avg, offline_avg, freetext_avg], ignore_index=True)

days_summary


# %%
benef = df_all[df_all['benefitted'] == 'Yes']
counts = (
    pd.crosstab(
        index=benef['office'],
        columns=benef['channel']
    )
    .reindex(columns=['online', 'offline', 'freetext'], fill_value=0)
)

counts['total_benefitted'] = counts.sum(axis=1)
perc = counts.div(counts['total_benefitted'], axis=0).mul(100).round(1)
perc = perc[['online', 'offline', 'freetext']].add_suffix('_benefitted_pct').reset_index()
perc

# %%
df_offline['grievance'].value_counts()

# %%
df_unique[df_unique['category'] == 'General & Misc']

# %%
df_unique['grievance'].value_counts()

# %%
df_unique[df_unique['category']=='General & Misc']['dept'].value_counts()

# %%
df_english[(df_english['grievance_category']=='Ration Card')&(df_english['subcategory']!='Ration Card Issue')]

# %%
df_english['subcategory'].value_counts()

# %%
df_english[(df_english['grievance_category']=='Ration Card')&(df_english['dept']=='Panchayati Raj & Drinking Water')]['mode'].value_counts()

# %%
df_english[df_english['grievance_category']=='Other']['dept'].value_counts()

# %%
len(df_english[(df_english['grievance_category']=='Other')&(df_english['dept']=="Revenue & Disaster Management")&(df_english['grievance'].str.lower().str.contains('land'))])

# %%
df_status2[df_status2['days_to_dispose'] > 50]

# %%
# client.get_action_history("CMO20241051399")


