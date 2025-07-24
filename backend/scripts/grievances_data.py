import pandas as pd
from tabulate import tabulate
import numpy as np
from functools import reduce

CHANNEL_MAP = {
    'Website': 'online', 'Whatsapp': 'online', 'Mobile': 'online',
    'Joint Hearing': 'offline', 'Physical': 'offline', 'CM Weekly Grievance': 'offline',
    'Letter': 'freetext', 'Email': 'freetext'
}
   
# Change the path to the directory where your JSON files are located

def load_grievances_data():
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
        if status == 1 or status == 2:
            # Convert all date columns from string to datetime (auto-detect format)
            date_cols = ['created_on', 'tagged_date', 'assigned_on', 'escalation_date', 'resolved_on']
            for col in date_cols:
                if col in df_status.columns:
                    df_status[col] = pd.to_datetime(df_status[col], unit='ms')

        df_status['status_id'] = status
        df_complaints = pd.concat([df_complaints, df_status], ignore_index=True)

    # Sort by ticket_no and then by the date priority
    df_complaints_sorted = df_complaints.sort_values(by=['ticket_no', 'created_on', 'escalation_date', 'resolved_on'])

    # Keep the first occurrence of each ticket_no
    df_unique = df_complaints_sorted.drop_duplicates(subset='ticket_no', keep='first').copy()
    df_unique['office'] = df_unique['office'].str.replace('Supertendent of Police', 'Superintendent of Police', regex=False)
    return df_unique

def overall_stats(data):
    df_counts = (data.groupby(['office', 'status_id']).size().reset_index(name='count'))
    office_totals = df_counts.groupby('office')['count'].sum().reset_index(name='total_complaints')
    df_counts = df_counts.merge(office_totals, on='office')
    df_counts['percentage'] = (df_counts['count'] / df_counts['total_complaints']) * 100
    df_counts['percentage'] = df_counts['percentage'].round(1)

    df_pivot = df_counts.pivot(index='office', columns='status_id', values=['count', 'percentage'])
    df_pivot.columns = [ f"count_statusid_{status}" if stat == 'count' else f"perc_statusid_{status}" for stat, status in df_pivot.columns]

    df_summary = office_totals.merge(df_pivot.reset_index(), on='office')
    df_summary.columns = ['office', 'total_complaints', 'count_unassigned',  'count_pending','count_disposed', 'perc_unassigned','perc_pending', 'perc_disposed']

    return df_summary

def get_status2_stats(data):
    df_status2 = data[data["status_id"] == 2].copy()
    df_status2['created_on'] = pd.to_datetime(df_status2['created_on'], errors='coerce')
    df_status2['days_to_dispose'] = (df_status2['resolved_on'] - df_status2['created_on']).dt.days
    df_status2['benefitted_bool'] = df_status2['benefitted'].map({'Yes': True, 'No': False})
    office_avg = df_status2.groupby('office')['days_to_dispose'].mean().round(0).reset_index()
    office_summary = (df_status2.groupby('office')['benefitted_bool'].agg(total_complaints='count',
                                                                          disposed_and_benefitted='sum').reset_index())
    # Calculate not-benefitted count
    office_summary['disposed_without_benefit'] = office_summary['total_complaints'] - office_summary['disposed_and_benefitted']

    # Compute percentages (rounded to 1 decimal)
    office_summary['percent_benefitted'] = (office_summary['disposed_and_benefitted'] / office_summary['total_complaints'] * 100).round(1)
    office_summary['percent_not_benefitted'] = (office_summary['disposed_without_benefit'] / office_summary['total_complaints'] * 100).round(1)

    # Sort by percent_benefitted 
    office_summary = office_summary.sort_values(by='percent_benefitted', ascending=False)

    df_benefitted = df_status2[df_status2['benefitted'] == 'Yes']
    avg_days_per_office_benefitted = df_benefitted.groupby('office')['days_to_dispose'].mean().round(0).reset_index()
    avg_days_per_office_benefitted = avg_days_per_office_benefitted.rename(columns={'days_to_dispose': 'days_to_benefit'})
    avg_days_per_office_benefitted = avg_days_per_office_benefitted.sort_values(by='days_to_benefit')
    avg_days_per_office_benefitted.round(0)

    merged1 = pd.merge(office_summary, office_avg, on='office', how='outer')
    final_merged = pd.merge(merged1, avg_days_per_office_benefitted, on='office', how='outer').fillna(0).round(1)

    return final_merged

def get_avg_time_metrics(data):
    df0 = data[data["status_id"] == 0].copy()
    df1 = data[data["status_id"] == 1].copy()
    df2 = data[data["status_id"] == 2].copy()

    today = pd.Timestamp('2025-06-22').normalize()

    df0['created_on'] = pd.to_datetime(df0['created_on'], errors='coerce')
    df0['days_without_assignment'] = (today - df0['created_on'].dt.normalize()).dt.days
    df0_summary = df0.groupby('office')['days_without_assignment'].mean().reset_index()

    df1['created_on'] = pd.to_datetime(df1['created_on'], errors='coerce')
    df1['days_open_without_disposal'] = (today - df1['created_on'].dt.normalize()).dt.days
    df1_summary = df1.groupby('office')['days_open_without_disposal'].mean().reset_index()

    df2['created_on'] = pd.to_datetime(df2['created_on'], errors='coerce')
    df2['days_to_dispose'] = (df2['resolved_on'] - df2['created_on']).dt.days
    df2_avg = df2.groupby('office')['days_to_dispose'].mean().reset_index()

    df2_benefitted = df2[df2['benefitted'] == 'Yes']
    df2_benefit_avg = df2_benefitted.groupby('office')['days_to_dispose'].mean().reset_index()
    df2_benefit_avg = df2_benefit_avg.rename(columns={'days_to_dispose': 'days_to_benefit'})

    # Rename for clarity
    def prefix_avg(df, key='office'):
        return df.rename(columns={col: f'avg_{col}' for col in df.columns if col != key})

    dfs = [df2_avg, df2_benefit_avg, df1_summary, df0_summary]
    dfs = [prefix_avg(df) for df in dfs]

    merged = reduce(lambda l, r: pd.merge(l, r, on='office', how='left'), dfs)
    return merged.fillna(0).round(0)


def response_time_across_offices(data):
    df_status2 = data[data["status_id"] == 2].copy()
    df_status2['created_on'] = pd.to_datetime(df_status2['created_on'], errors='coerce')
    df_status2['days_to_dispose'] = (df_status2['resolved_on'] - df_status2['created_on']).dt.days
    avg_days_per_benefit_status = df_status2.groupby('benefitted')['days_to_dispose'].mean().reset_index()
    avg_days_per_benefit_status.round(0)
    df_status2['benefitted_bool'] = df_status2['benefitted'].map({'Yes': True, 'No': False})
    office_avg = df_status2.groupby('office')['days_to_dispose'].mean().round(0).reset_index()
    office_summary = (df_status2.groupby('office')['benefitted_bool'].agg(total_complaints='count',
                                                                          disposed_and_benefitted='sum').reset_index())
    # Calculate not-benefitted count
    office_summary['disposed_without_benefit'] = office_summary['total_complaints'] - office_summary['disposed_and_benefitted']

    # Compute percentages (rounded to 1 decimal)
    office_summary['percent_benefitted'] = (office_summary['disposed_and_benefitted'] / office_summary['total_complaints'] * 100).round(1)
    office_summary['percent_not_benefitted'] = (office_summary['disposed_without_benefit'] / office_summary['total_complaints'] * 100).round(1)

    # Sort by percent_benefitted 
    office_summary = office_summary.sort_values(by='percent_benefitted', ascending=False)



def category_investigation(data):
    data['category'] = data['category'].replace(
    {'General': 'General & Misc', 'Miscellaneous': 'General & Misc'}) # Merge the 2 categories

    cat_count = data['category'].value_counts()
    cat_percent = data['category'].value_counts(normalize=True).mul(100).round(1)

    cat_summary = pd.DataFrame({'count': cat_count, 'percent': cat_percent})
    print("Category Overview")
    print(cat_summary)

    print("Diving Deeper into Social Welfare")
    print(data[(data['category']=='Social Welfare')]['dept'].value_counts())

    def assign_category(text):
        housing_keys = ['pmay', 'pmagy', 'housing', 'awas', 'yojana', 'yojna', 'house']
        if any(key in text for key in housing_keys):
            return 'Housing'
        elif 'subhadra' in text:
            return 'Subhadra Scheme'
        elif 'ration card' in text:
            return 'Ration Card'
        else:
            return 'Other'

    data['grievance_category'] = data['grievance'].str.lower().apply(assign_category)

    def is_mostly_ascii(text, threshold=0.9):
        if not isinstance(text, str):
            return False
        ascii_chars = sum(c.isascii() for c in text)
        return ascii_chars / len(text) >= threshold

    df_english = data[data['grievance'].apply(is_mostly_ascii)] # function to filter exclusively english complaints 

    print("Looking at New Categories within Social Welfare and Panchayati Raj & Drinking Water Department:")
    count = df_english[(df_english['category']=='Social Welfare') & (df_english['dept']=='Panchayati Raj & Drinking Water')]['grievance_category'].value_counts()
    percent = df_english[(df_english['category']=='Social Welfare') & (df_english['dept']=='Panchayati Raj & Drinking Water')]['grievance_category'].value_counts(normalize=True).mul(100).round(1)
    summary = pd.DataFrame({'count': count, 'percent': percent})
    return summary 

def resolution_times(data):
    df_online_resolution, df_online_benefitted_avg = channel_stats("online", data)
    df_offline_resolution, df_offline_benefitted_avg = channel_stats("offline", data)
    df_freetext_resolution, df_freetext_benefitted_avg = channel_stats("freetext", data)
    dfs = [df_online_resolution, df_offline_resolution, df_freetext_resolution, df_online_benefitted_avg,df_offline_benefitted_avg, df_freetext_benefitted_avg]
    df_merged_resolution = reduce(lambda left, right: pd.merge(left, right, on='office', how='left'),
                   dfs)

    df_merged_resolution = df_merged_resolution.fillna(0).round(0)

    # Convert float columns to int after rounding
    float_cols = df_merged_resolution.select_dtypes(include=['float']).columns
    for col in float_cols:
        df_merged_resolution[col] = df_merged_resolution[col].astype(int)
    
    return df_merged_resolution


def channel_stats(channel, data):
    df = data[data['mode'].map(CHANNEL_MAP) == channel].copy()
    df['created_on'] = pd.to_datetime(df['created_on'])
    df['resolved_on'] = pd.to_datetime(df['resolved_on'])
    today = pd.Timestamp('2025-06-22').floor('D')

    days_open_col = f'days_open_{channel}'
    avg_open_col = f'avg_days_open_{channel}'
    benefit_col = f'avg_days_to_benefit_{channel}'

    # Calculate days open
    df[days_open_col] = np.where(
        df['resolved_on'].notna(),
        (df['resolved_on'] - df['created_on']).dt.days,
        (today - df['created_on']).dt.days
    )

    # Average open days per office
    resolution = df.groupby('office', as_index=False).agg({days_open_col: 'mean'}).rename(columns={days_open_col: avg_open_col})

    # Benefitted only
    df_benefitted = df[df['benefitted'] == "Yes"]
    benefitted_avg = df_benefitted.groupby('office', as_index=False).agg({days_open_col: 'mean'}).rename(columns={days_open_col: benefit_col})
    
    return resolution, benefitted_avg

def mode_summary_table(data):
    mode_map = {
        'online': ['Website', 'Whatsapp', 'Mobile'],
        'offline': ['Joint Hearing', 'Physical', 'CM Weekly Grievance'],
        'freetext': ['Letter', 'Email']
    }

    today = pd.Timestamp('2025-06-22').floor('D')
    rows = []

    for mode, modes_list in mode_map.items():
        df_mode = data[data['mode'].isin(modes_list)].copy()
        if df_mode.empty:
            rows.append({
                'mode': mode,
                'total': 0,
                'benefitted': 0,
                'benefitted_rate_%': 0,
                'avg_days_till_benefit': None,
                'avg_days_till_disposed': None
            })
            continue

        df_mode['created_on'] = pd.to_datetime(df_mode['created_on'], errors='coerce')
        df_mode['resolved_on'] = pd.to_datetime(df_mode['resolved_on'], errors='coerce')

        # Calculate days to disposal (resolved - created or today - created if unresolved)
        df_mode['days_to_dispose'] = np.where(
            df_mode['resolved_on'].notna(),
            (df_mode['resolved_on'] - df_mode['created_on']).dt.days,
            (today - df_mode['created_on']).dt.days
        )

        total = len(df_mode)
        df_benefitted = df_mode[df_mode['benefitted'] == 'Yes']
        benefitted = len(df_benefitted)
        benefitted_rate = (benefitted / total * 100) if total > 0 else 0

        avg_days_benefit = df_benefitted['days_to_dispose'].mean() if benefitted > 0 else None
        avg_days_disposed = df_mode['days_to_dispose'].mean() if total > 0 else None

        rows.append({
            'mode': mode,
            'total': total,
            'benefitted': benefitted,
            'benefitted_rate_%': round(benefitted_rate, 1),
            'avg_days_till_benefit': round(avg_days_benefit, 1) if avg_days_benefit is not None else None,
            'avg_days_till_disposed': round(avg_days_disposed, 1) if avg_days_disposed is not None else None
        })

    return pd.DataFrame(rows)

def office_model_channel_summary(data):
    props = data.groupby('office')['mode'].value_counts(normalize=True).mul(100).round(1).rename('percent').reset_index()
    office_mode_pct = props.pivot(index='office', columns='mode', values='percent').fillna(0).reset_index()

    data['channel'] = data['mode'].map(CHANNEL_MAP).fillna('Urgent')
    data = data[data['channel'] != 'Urgent']

    counts = pd.crosstab(data['office'], data['channel'])
    percents = pd.crosstab(data['office'], data['channel'], normalize='index').mul(100).round(1)

    office_summary = (counts.add_suffix('_count').join(percents.add_suffix('_percent')).reset_index())

    return office_mode_pct, office_summary

def benefitted_pct_by_channel(data):
    # First, map mode → channel
    channel_map = {
        'Website': 'online', 'Whatsapp': 'online', 'Mobile': 'online',
        'Joint Hearing': 'offline', 'Physical': 'offline', 'CM Weekly Grievance': 'offline',
        'Letter': 'freetext', 'Email': 'freetext'
    }
    data = data.copy()
    data['channel'] = data['mode'].map(channel_map).fillna('unknown')
    data = data[data['channel'].isin(['online', 'offline', 'freetext'])]
    data_benefitted = data[data['benefitted'] == 'Yes']
    total_benefitted = data_benefitted.groupby('office').size().rename("total_benefitted")
    office_channel_counts = (
        data_benefitted
        .groupby(['office', 'channel'])
        .size()
        .unstack(fill_value=0)
    )
    office_channel_pct = (
        office_channel_counts
        .div(office_channel_counts.sum(axis=1), axis=0)
        .mul(100)
        .round(1)
        .add_suffix('_benefitted_pct')
        .reset_index()
    )

    return office_channel_pct

def channel_overview(df, channel):
    df = df.copy()
    df['channel'] = df['mode'].map(CHANNEL_MAP).fillna('Urgent')
    df_filtered = df[df['channel'] == channel]
    office_counts = (df_filtered['office'].value_counts(dropna=False).rename_axis('office').reset_index(name='count'))
    total = office_counts['count'].sum()
    office_counts['percent'] = (office_counts['count'] / total * 100).round(1)
    office_counts = office_counts.sort_values(by='count', ascending=False).reset_index(drop=True)

    dept_counts = (df_filtered['dept'].value_counts(dropna=False).rename_axis('dept').reset_index(name='count'))
    total = dept_counts['count'].sum()
    dept_counts['percent'] = (dept_counts['count'] / total * 100).round(1)
    dept_counts = dept_counts.sort_values(by='count', ascending=False).reset_index(drop=True)

    cat_counts = (df_filtered['category'].value_counts(dropna=False).rename_axis('category').reset_index(name='count'))
    total = cat_counts['count'].sum()
    cat_counts['percent'] = (cat_counts['count'] / total * 100).round(1)
    cat_counts = cat_counts.sort_values(by='count', ascending=False).reset_index(drop=True)

    return office_counts, dept_counts, cat_counts
    
if __name__ == "__main__":
    data = load_grievances_data()
    print("Number of complaints in 2025:", len(data))
    overall = overall_stats(data)
    print("Overall Statistics:")
    print(tabulate(overall, headers='keys', tablefmt='pretty'))
    print("Status 2 Complaints Statistics:")
    status2_stats = get_status2_stats(data)
    print(status2_stats)
    print("Category Investigation:")
    cat_investigation = category_investigation(data)
    print(cat_investigation)
    print("Resolution Times:")
    resolution_output = resolution_times(data)
    print(resolution_output)
    resolution_offices = get_avg_time_metrics(data)
    print(resolution_offices)
    print("Channel Response Times:")
    channel_response_times_table = mode_summary_table(data)
    print(channel_response_times_table)
    print("Office Channel Stats:")
    office_mode_pct, office_summary = office_model_channel_summary(data)
    print(office_mode_pct)
    print(office_summary)
    print("Benefitted % By Channel")
    office_channel_pct = benefitted_pct_by_channel(data)
    print(office_channel_pct)
    print("Online Channels Overview:")
    online_office_counts, online_dept_counts, online_cat_counts = channel_overview(data, "online")
    print(online_office_counts)
    print(online_dept_counts)
    print(online_cat_counts)
    print("Offline Channels Overview:")
    offline_office_counts, offline_dept_counts, offline_cat_counts = channel_overview(data, "offline")
    print(offline_office_counts)
    print(offline_dept_counts)
    print(offline_cat_counts)







