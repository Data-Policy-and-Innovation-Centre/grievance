# %%
import requests
from app.ingestion.client import JanasunaniAPIClient, JanasunaniAPIError
from app.ingestion.schemas import validate, validate_action_history, Complaint, District
from app.ingestion import OFFICE, STATUS
import pandas as pd
from pathlib import Path
import time

# %% [markdown]
# # Summary of results for status == 1 (Registered and assigned):
# 
# - Jan2025-Jun2025 for all districts and all offices
# - Total complaints: 57,903
# - There are some columns that has no information.
#     - Complaints: `block`(23% missings), `tagged_date` (93%), tagged_to (92%), tagged_by (93%)
#     - Actions: `action_taken_date` (100% missings)
# - In general, the column `grievance` appears to be a classification of the grievance according to some officer.
#     - 26,226 of grievances has less than 50 characters (45%).
#     - ‘common’ grievances repressent 39% of the total complaints.
# - The most common mode is Website (35.8%), followed by Joint Hearings (20.8%), Physical (14.7%), Letter (10.3%) and WhatsApp (8.6%).
# - 35.3% of the complaints are categorized as “General” or “Miscelaneous” → There is some space to improve categorization.
# - Analysis by mode
#     - Website:
#         - There is evidence of SPAM
#         - The `grievance` column appears to be a simplified version of the grievance.
#     - Joint Hearings, Physical, Letter and Email:
#         - The column grievance appears to be a summary made by one official.
#         - This is not the case for WhatsApp and Mobile -> appears to represent fairly the complaints of the citizens
#     - Letter:
#         - 15% of complaints are enclosed and the column grievance does not say anything about the topic.
#     - WhatsApp:
#         - There is evidence of SPAM: phone numbers with 10+ complaints account for 28% of WhatsApp complaints.

# %% [markdown]
# - Have a big picture of number of complaints by status and mode
# - Check if block/Addres missings by mode. 
# - Always use percentages.
# - financial help -> to who office is going? Where is it comming from?
# - Categorized on Joint H, Physical and CM Meetings
# - for pending -> How many time is that.

# %% [markdown]
# # Fetching data from Jana Sunani

# %%
raw = Path("D:/1. Documentos/0. Bases de datos/00. GitHub/grievance/backend/data/raw")
        
client = JanasunaniAPIClient()

try:
    districts = client.get_districts()
    districts_validated = validate(districts, District)
    
    offices = OFFICE.keys()

    action_lst = []
    complaints_lst = []
    for d in districts_validated:
        for office in offices:
            try:
                complaints = client.get_complaints(2025, status=2, distId=d['dist_id'], office=office)
                complaints_validated = validate(complaints, Complaint)
                complaints_lst.extend(complaints_validated)

            except JanasunaniAPIError as e:
                continue
            
except requests.RequestException as e:
    print(f"An error occurred: {e}")

df_2 = pd.DataFrame(complaints_lst)
raw = Path("D:/1. Documentos/0. Bases de datos/00. GitHub/grievance/backend/data/raw")
df_2.to_json(raw / "grievances2025_2.json")

# %%
df_1.duplicated(subset=['ticket_no']).sum()

# %%
df_0 = pd.DataFrame(complaints_lst)
raw = Path("D:/1. Documentos/0. Bases de datos/00. GitHub/grievance/backend/data/raw")
df_0.to_json(raw / "grievances2025_0.json")

# %%
df_0.shape

# %% [markdown]
# # Analysis for Complaints

# %%
# df = pd.DataFrame(complaints_lst)

# %%
df_0

# %% [markdown]
# ## General skim of dataframe

# %% [markdown]
# Grievances:
# 
# - The column `block` is missing 77% of the time
# - `tagged_to`, `tagged_by`, `tagged_date`, resolved_on are always null (92.7% missing in `tagged_date`)
# - `govt_ticket` is almost always False (0.0053% True)
# - In general, the column `grievance` it appears to be sometimes a classification of the grievance according to some officer, and other times it’s the actual grievance.

# %%


# %%
import skimpy
skimpy.skim(df)

# %%
df[df['mode'] == "Website"]['block'].isna().sum()

# %% [markdown]
# ## Grievances by date

# %% [markdown]
# Complaints are more frequent on weekdays 8K+ daily, than on weekends (4K+)

# %%
df['created_on'] = pd.to_datetime(df['created_on'], unit='ms')
df.created_on.dt.day_name().value_counts().reset_index()

# %%
df.created_on.dt.month_name().value_counts().reset_index()

# %% [markdown]
# ## Grievances by District

# %%
df.district.value_counts().reset_index()

# %% [markdown]
# ## Grievances by Office

# %%
df[df['mode'].isin(['Website', 'Whatsapp', 'Mobile'])].office.value_counts().reset_index()

# %%
df[(df['mode'].isin(['Website', 'Whatsapp', 'Mobile'])) & (df['office'] == 'Office of Chief Minister')]['dept'].value_counts().reset_index()

# %%
df[(df['mode'].isin(['Website', 'Whatsapp', 'Mobile'])) & (df['office'] == 'Office of Chief Minister')]['subcategory'].value_counts().reset_index()

# %% [markdown]
# There are a lot of 'General' and 'Miscellaneous' complaints (35.3%)

# %%
grievances_by_category = df[df['office'] == "Office of Chief Minister"].category.value_counts().reset_index()
grievances_by_category['pct'] = (grievances_by_category['count'] / grievances_by_category['count'].sum()*100).round(1)
grievances_by_category

# %% [markdown]
# Social Welfare, Service Matter, Financial Assistance
# Education vs School & College
# CMRF - Financial

# %% [markdown]
# ## Grievances by mode

# %%
grievances_by_mode = df['mode'].value_counts().reset_index()
grievances_by_mode['pct'] = (grievances_by_mode['count'] / grievances_by_mode['count'].sum()*100).round(1)
grievances_by_mode

# %%
df_mode_griev = df.groupby(['mode','grievance']).size().reset_index(name='count').sort_values(by='count', ascending=False)

df_mode_griev['repeated_grievance'] = (df_mode_griev['count'] > 10)
df_mode_griev['length'] = df_mode_griev['grievance'].apply(lambda x: len(x))
df_mode_griev['classified_grievance'] = (df_mode_griev['length'] > 10) & (df_mode_griev['repeated_grievance'] == True)

# %%
# Display grievances by mode and repeated grievances
df_mode_repeated = df_mode_griev[df_mode_griev['repeated_grievance']].groupby('mode')['count'].sum().reset_index().sort_values(by='count', ascending=False).merge(grievances_by_mode, on='mode', how='left')
df_mode_repeated['pct'] = (df_mode_repeated['count_x'] / df_mode_repeated['count_y']*100).round(2)
df_mode_repeated

# %%
# Display grievances by mode and repeated grievances
df_mode_classified = df_mode_griev[df_mode_griev['classified_grievance']].groupby('mode')['count'].sum().reset_index().sort_values(by='count', ascending=False).merge(grievances_by_mode, on='mode', how='left')
df_mode_classified['pct'] = (df_mode_classified['count_x'] / df_mode_classified['count_y']*100).round(2)
df_mode_classified

# %%
df_mode_griev[df_mode_griev['classified_grievance']].groupby('mode')['count'].sum().reset_index().sort_values(by='count', ascending=False)

# %% [markdown]
# ## Grievances text analysis

# %%
df = pd.DataFrame(complaints_lst)
df['grievance'] = df['grievance'].str.lower()

# %% [markdown]
# #### 0. General

# %% [markdown]
# Total: 57,421
# Distinct grievances: 39,494
# Frequent grievances: 4,532 

# %%
df.shape

# %%
distinct_g = df['grievance'].value_counts().reset_index()
len(distinct_g)

# %%
distinct_g['length'] = distinct_g['grievance'].apply(lambda x: len(x))

# %%
distinct_g[distinct_g['length'] < 100]['count'].sum()

# %%
len("ଆର୍ଥିକ ସହାୟତା ପାଇବା ପାଇଁ ଆପଣଙ୍କୁ ଅନୁରୋଧ କରୁଅଛି |")

# %%
distinct_g[distinct_g['count'] > 1]['count'].sum()

# %% [markdown]
# #### 1. Website analysis

# %% [markdown]
# Total: 20,455
# Distinct grievances: 15,593
# Frequent: 1,748 (32.3% of Total)

# %% [markdown]
# We might need to clarify if ALL of these are the actual grievance from the citizen, as some appears to be really simple/direct and same written. Some examples:
# - 'financial help' and its variations in english and oria (+6%)
# - pradhan mantri awas yojana and its variations
# - widow person and its variations
# 
# There are some examples of SPAM. Example:
# - "୧)କନିଷ୍ଠ ଶିକ୍ଷକ (ଯୋଜନା ଭିତ୍ତିକ) ମାନେ ନିଯୁକ୍ତ ହେବାର ଦୀର୍ଘ ୩ ମାସ ରୁ ଉର୍ଦ୍ଧ୍ବ ସମୟ ବିତିଯାଇଥିଲେ ମଧ୍ୟ ଅଧିକାଂଶ ଜିଲ୍ଲା ରେ ଦରମା ମିଳିନାହିଁ,ଉପରିସ୍ଥ ଅଧିକାରୀ ଙ୍କୁ ଭେଟିଲା ପରେ ସେମାନଙ୍କ ଉତ୍ତର ଯେ ଓସେପା ଅର୍ଥ ଫେରେଇ ନେଇଛି, ଡ଼ିଜିଗଭ (digi gov) କାମ କରୁନାହିଁ,...."
# - "ମୁଁ ପବିତ୍ର କୁମାର ଦାଶ ଅତ୍ୟନ୍ତ ...."
# - "respected sir/madam, i am writing to respectfully request consideration for amending the qualification requirements for the stenographer post in the water resources department, government of odisha. specifically, i propose changing the requirement from a compulsory iti stenography certificate to a government-recognized institute's stenography certificate."
# 

# %%
distinct_g_web = df[(df['mode'] == "Website")]['grievance'].value_counts().reset_index()
distinct_g_web[distinct_g_web['count'] > 1]

# %% [markdown]
# Example of spam

# %%
df[df['grievance'].str.contains('spected sir/madam')]

# %% [markdown]
# #### 2. Joint Hearings analysis

# %% [markdown]
# Total: 12,062
# Distinct grievances: 6,974
# Frequent: 1,081 (88.5% of Total)

# %% [markdown]
# - In the case of Joint Hearings, the column `grievance` appears to be a summary made by one official, not the actual grievance.
# - 494 complaints have "grievance matter attached" as `grievance` (4.1%). 
# - 180 complaints are empty "." (1.5%)

# %%
distinct_g_jh = df[(df['mode'] == "Joint Hearing")]['grievance'].value_counts().reset_index()
distinct_g_jh[distinct_g_jh['count'] > 1]

# %%
distinct_g_jh[distinct_g_jh['count'] == 1]

# %% [markdown]
# #### 3. Physical analysis

# %% [markdown]
# Total: 8,437
# Distinct grievances: 5,229
# Frequent: 649 (73.8% of Total)

# %% [markdown]
# - In the case of Physical complaints, the column `grievance` appears to be a summary made by one official, not the actual grievance.

# %%
distinct_g_phy = df[(df['mode'] == "Physical")]['grievance'].value_counts().reset_index()
distinct_g_phy[distinct_g_phy['count'] > 1]

# %%
distinct_g_phy[distinct_g_phy['count'] == 1]

# %% [markdown]
# #### 4. Letter analysis

# %% [markdown]
# Total: 5,957
# Distinct grievances: 4,339
# Frequent: 361 (45.6% of Total)

# %% [markdown]
# - In the case of Letter complaints, the column `grievance` appears to be a summary made by one official in most of the cases, not the actual grievance.
# - 14.4% of letter complaints are enclosed and the column `grievance` does not say anything about the topic.

# %%
distinct_g_let = df[(df['mode'] == "Letter")]['grievance'].value_counts().reset_index()
distinct_g_let[distinct_g_let['count'] > 1]

# %%
distinct_g_let[(distinct_g_let['count'] == 1) & (~distinct_g_let['grievance'].str.contains('regarding')) & (~distinct_g_let['grievance'].str.contains('petition of'))  & (~distinct_g_let['grievance'].str.contains('allegation against'))]

# %% [markdown]
# #### 5. WhatsApp analysis

# %% [markdown]
# Total: 4,910
# Distinct grievances: 4,066
# Frequent: 353 (29.4%)

# %% [markdown]
# - There are some SPAM occurances. Examples:
#     - "please immediately take a judicial action as per my grievance enclosed my grievance copy" 158 complaints from same petitioner (3.2%)
#     - "• my rehabilitation & resettlement(r&r) issue for phase-2 area of jindal steel & power limited, angul is pending since more than 18 years...." 84 complaints from same mobile phone, different petitioner name. 
# - There might be problems addressing the actual complaint (Example: 'Hi')
# - Numbers with 10+ complaints account for 28.2% of the complaints in WhatsApp.

# %%
distinct_g_wa = df[(df['mode'] == "Whatsapp")]['grievance'].value_counts().reset_index()
distinct_g_wa[distinct_g_wa['count'] > 1]

# %%
petitioners_wa = df[(df['mode'] == "Whatsapp")]['petitioner_mobile'].value_counts().reset_index()
petitioners_wa[petitioners_wa['count'] > 10]['count'].sum()

# %%
repeated_df_wa = df[(df['mode'] == "Whatsapp") & df['petitioner_mobile'].isin(petitioners_wa[petitioners_wa['count'] > 1]['petitioner_mobile'])]
repeated_df_wa['created_on'] = pd.to_datetime(repeated_df_wa['created_on'], unit = 'ms')

# %%
repeated_df_wa.sort_values(by=['petitioner_mobile', 'created_on'])

# %%
df[df['grievance'].str.contains("ମୁଁ ପବିତ୍ର କୁମାର ଦାଶ ଅତ୍ୟନ୍ତ")]

# %% [markdown]
# #### 6. Mobile

# %% [markdown]
# Total: 2,513
# Distinct grievances: 2,229
# Frequent grievances: 171 (18.1%)

# %% [markdown]
# In the case of Mobile complaints, the column `grievance` appear to represent fairly the complaints of the citizens. They are not classified or summarized by some official.

# %%
distinct_g_mo = df[(df['mode'] == "Mobile")]['grievance'].value_counts().reset_index()
distinct_g_mo[distinct_g_mo['count'] > 1]

# %% [markdown]
# #### 7. Email

# %% [markdown]
# Total: 2,191
# Distinct grievances: 1,328
# Frequent grievances: 151 (46.3%)

# %% [markdown]
# - In the case of Email complaints, the column `grievance` appears to be a summary made by one official in most of the cases, not the actual grievance.
# - Example: 
#     - 'prayer for redressal...' and its variations represent the 35.6% of the Email complaints.
#     - 'grievance petition of...' and its variations represent the 27.2% of the Email complaints.

# %%
distinct_g_em = df[(df['mode'] == "Email")]['grievance'].value_counts().reset_index()
distinct_g_em[distinct_g_em['count'] > 1]

# %%
df[(~df['grievance'].str.contains('prayer for redressal')) & (df['mode'] == "Email") & (~df['grievance'].str.contains('grievance petition of'))]['grievance'].value_counts()

# %% [markdown]
# # Actions

# %% [markdown]
# The column `action_taken_date` is always missing. 

# %%
import pandas as pd
df_actions = pd.DataFrame(action_lst)

# %%
import skimpy
skimpy.skim(df_actions)

# %%
len(df_actions['ticket_no'].unique())

# %%
df_actions['action_taken_remark'].value_counts().reset_index()

# %%
df[df['ticket_no'] == "GOV20251080121"]

# %%
df_actions[df_actions['ticket_no'] == "GOV20251080121"]

# %%
df_actions['action_status'].unique()

# %%
status_dummies = pd.get_dummies(df_actions['action_status'])

df_actions = pd.concat([df_actions, status_dummies], axis=1)

# %%
status_dummies.columns

# %%
df_actions[df_actions['Reminder Sent']]

# %%
df_tokens_actions = df_actions.groupby('ticket_no')[status_dummies.columns].sum().reset_index()

# %%
client = JanasunaniAPIClient()
action_history = client.get_action_history('CMO20251141611')
action_history2 = validate_action_history(action_history,'CMO20251141611')

# %%
action_history2

# %%
action_history

# %%
df_tokens_actions

# %%
cond_assigned = df_tokens_actions['Complaint Assigned'] > 0 
cond_registered = df_tokens_actions['Complaint Register'] > 0 
cond_replied = df_tokens_actions['Replied'] > 0 

# %%
df_tokens_actions[cond_assigned & cond_registered].sum()

# %%
df_tokens_actions['sum'] = df_tokens_actions[['Complaint Assigned', 'Complaint Pullback', 'Complaint Register',
       'Complaint Transfer', 'Discard', 'Forward', 'Forwarded To Subordinate',
       'Reminder Sent', 'Reopen', 'Replied']].sum(axis=1)

# %%
df_tokens_actions['sum'].value_counts().reset_index()

# %%
rare_tokens = df_tokens_actions.loc[df_tokens_actions['sum'] > 7,'ticket_no']

# %%
df_actions[df_actions['ticket_no'].isin(rare_tokens)]

# %% [markdown]
# # Saving into json files

# %%
df.to_json(raw / "grievances2025.json")

# %%
df_actions.to_json(raw / "actions_sample2025.json")

# %% [markdown]
# # Analysis on Chief Minister Action History

# %%
# Importing the ticket numbers from the actions file
from pathlib import Path
import json
raw = Path("D:/1. Documentos/0. Bases de datos/00. GitHub/grievance/backend/data/raw")

with open(raw/"dic_tickets.json", "r") as file:
    dic_tickets = json.load(file)

client = JanasunaniAPIClient()

# %%
lst_cmo_ben = dic_tickets['Office of Chief Minister']['Yes']

# %%
lst_cs_ben = dic_tickets['Chief Secretary']['Yes']

# %%
def fetch_actions_from_list(lst_tickets: list[str]) -> pd.DataFrame:
    actions = []
    for ticket in lst_tickets:
        try:
            action_history = client.get_action_history(ticket)
            action_history = validate_action_history(action_history, ticket)
            actions.extend(action_history)
        except JanasunaniAPIError as e:
            print(f"Error fetching action history for {ticket}: {e}")

    actions_df = pd.DataFrame(actions)

    return actions_df

def transform_actions(actions_df: pd.DataFrame) -> pd.DataFrame:
    reg_fw = actions_df[actions_df['action_status'].isin(['Complaint Register', 'Forward', 'Forwarded To Subordinate'])]
    days_to_fw = reg_fw.groupby('ticket_no')['action_taken_date'].agg(lambda x: (x.max() - x.min()).total_seconds()/86400).round(1).reset_index().rename(columns={'action_taken_date': 'days_to_fw'})
    total_days = actions_df.groupby('ticket_no')['action_taken_date'].agg(lambda x: (x.max() - x.min()).total_seconds()/86400).round(1).reset_index().rename(columns={'action_taken_date': 'total_days_diff'})
    summary_df = total_days.merge(days_to_fw, on='ticket_no', how='left')
    summary_df['potential_savings'] = (summary_df['days_to_fw'] / summary_df['total_days_diff']*100).round(1)

    return summary_df

# %%
summar_cs = fetch_actions_from_list(lst_cs_ben[:100])

# %%
summar_cs.to_json(raw / "cs_actions.json")

# %%
summary = transform_actions(summar_cs)

# %%
summary


