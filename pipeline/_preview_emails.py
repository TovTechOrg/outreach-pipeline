import sys, pandas as pd
sys.path.insert(0, 'pipeline')
from step6_send_emails import build_email

df = pd.read_csv('data/enriched_prospects.csv', low_memory=False).fillna('')
tier1 = df[(df['tier'] == 'Tier1') & (df['specific_achievement'].str.strip() != '')].head(3)

for _, row in tier1.iterrows():
    contact = {
        'org_name':             row['org_name'],
        'tier':                 row['tier'],
        'project_name':         str(row.get('project_titles', '')).split(' | ')[0][:80],
        'specific_achievement': row.get('specific_achievement', ''),
        'their_population':     row.get('their_population', ''),
        'relevant_theme':       row.get('relevant_theme', ''),
    }
    subj, body = build_email(contact, 'initial', 'tok')
    print('=' * 60)
    print('TO     :', str(row.get('email', '')).split(' | ')[0])
    print('SUBJECT:', subj)
    print()
    print(body)
    print()
