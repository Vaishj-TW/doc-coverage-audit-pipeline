import os
import json
import requests

# STEP 1: Read inputs
ANTHROPIC_API_KEY = os.environ['ANTHROPIC_API_KEY']
DOC360_API_KEY = os.environ['DOC360_API_KEY']
PR_TITLE = os.environ.get('PR_TITLE', 'untitled PR')
PR_BODY = os.environ.get('PR_BODY', 'no description provided')

with open('pr_diff.txt', 'r') as f:
    diff = f.read()

if not diff.strip():
    with open('audit_findings.md', 'w') as f:
        f.write('## Doc Coverage Audit\n\nNo code changes detected in this PR.')
    exit()

# STEP 2: Search Doc360 for related articles
doc360_headers = {'api_token': DOC360_API_KEY}
search_resp = requests.get(
    'https://apihub.document360.io/v2/articles/search',
    headers=doc360_headers,
    params={'query': PR_TITLE, 'limit': 10}
)

try:
    articles_raw = search_resp.json()
    articles = [
        {'title': a.get('title'), 'slug': a.get('slug')}
        for a in articles_raw.get('data', {}).get('articles', [])
    ]
except Exception:
    articles = []

# STEP 3: Build the prompt for Claude
prompt = f'''
You are a technical documentation auditor for a SaaS compliance platform called Scrut.
A pull request has just been merged. Identify documentation gaps.

PR Title: {PR_TITLE}
PR Description: {PR_BODY}

Code changes (diff):
<diff>
{diff[:8000]}
</diff>

Existing help center articles:
<articles>
{json.dumps(articles, indent=2)}
</articles>

Return findings in this format:
### Articles to Update
### New Articles to Create
### No Action Needed
'''

# STEP 4: Call the Claude API
response = requests.post(
    'https://api.anthropic.com/v1/messages',
    headers={
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    },
    json={
        'model': 'claude-sonnet-4-6',
        'max_tokens': 2000,
        'messages': [{'role': 'user', 'content': prompt}]
    }
)

resp_json = response.json()
if 'content' not in resp_json:
    raise Exception(f'Claude API error: {resp_json}')

findings = resp_json['content'][0]['text']

# STEP 5: Write the output file
with open('audit_findings.md', 'w') as f:
    f.write('## Doc Coverage Audit\n\n')
    f.write(f'**PR:** {PR_TITLE}\n\n')
    f.write('---\n\n')
    f.write(findings)
