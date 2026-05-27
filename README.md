# Doc Coverage Audit Pipeline

A GitHub Actions pipeline that automatically identifies documentation gaps whenever a pull request is merged. Built to solve a problem that affects every docs team: finding out about shipped features too late.

---

## The Problem

Documentation updates depend on writers manually tracking engineering changes. In practice, this means:

- Features ship without corresponding help center updates
- Deprecated features remain documented as if it still works
- There is no reliable signal for what changed unless a developer proactively reaches out

This pipeline eliminates that dependency.

---

## How It Works

Every time a pull request is merged, the pipeline runs automatically:

```
PR merged → GitHub Actions triggers → diff captured → Doc360 searched (Sample Tool) → Claude audits → findings posted as PR comment
```

| Step | What Happens |
|------|-------------|
| PR Merged | A developer merges a pull request on GitHub |
| Workflow Triggers | GitHub Actions detects the merge and starts the audit job |
| Diff Captured | The pipeline captures exactly which lines were added, changed, or removed |
| Help Center Searched | The pipeline queries Doc360 for articles related to the PR |
| Claude Audits | The diff and existing articles are sent to Claude, which analyzes the changes from a documentation perspective |
| Findings Posted | Claude's findings are posted as a structured comment directly on the merged PR |

---

## Example Output

The comment below was generated from a real test run on a SCIM provisioning PR. No human intervention was involved.

> **📋 Doc Coverage Audit — PR: Add SCIM provisioning for Okta**
>
> **Articles to Update**
> No existing articles require updates. There are no pre-existing help center articles covering Okta SCIM provisioning.
>
> **New Articles to Create**
> 1. Setting Up SCIM Provisioning with Okta
>    - What SCIM provisioning is and why it is useful
>    - Prerequisites: Okta admin access, Scrut admin role, SCIM endpoint and token details
>    - Step-by-step setup in both Okta and Scrut
>    - What happens when a user is deactivated in Okta
>    - Common errors and how to resolve them
>
> 2. Managing User Access with Okta and Scrut Automation
>    - Important limitation: Group Sync removed. Automatic mapping of Okta groups to Scrut roles is not supported. This must be clearly documented as a known gap to prevent admin confusion.

---

## Tech Stack

- **GitHub Actions** — workflow orchestration and PR comment delivery
- **Python** — audit script (`scripts/doc_audit.py`)
- **Claude API (Anthropic)** — documentation gap analysis
- **Doc360 API** — help center search

---

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── doc-audit.yml      # Workflow: when to run and what steps to execute
└── scripts/
    └── doc_audit.py           # Script: diff capture, Doc360 search, Claude call, output
```

---

## Setup

### Prerequisites

| Requirement | Details |
|-------------|---------|
| GitHub repo with write/admin access | The repo where PRs are merged |
| Anthropic API key | Available from [console.anthropic.com](https://console.anthropic.com) |
| Doc360 API token | Available from Doc360 dashboard under Settings > API Tokens |
| GitHub Actions enabled | Confirm under Settings > Actions > General |

---

### Phase 1 — Enable GitHub Actions write permissions

The workflow needs permission to post comments on pull requests.

1. Go to your repo **Settings > Actions > General**
2. Scroll to **Workflow permissions**
3. Select **Read and write permissions**
4. Click **Save**

Without this step, the final workflow step fails with: `HttpError: Resource not accessible by integration`.

---

### Phase 2 — Add API keys as repository secrets

1. Go to **Settings > Secrets and variables > Actions**
2. Click **New repository secret**
3. Add the following:

| Secret Name | Value |
|-------------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `DOC360_API_KEY` | Your Doc360 API token |

GitHub encrypts these at rest and injects them only at runtime. The values are never visible after saving.

---

### Phase 3 — Create the workflow file

1. In the repo, click **Add file > Create new file**
2. In the filename field, type: `.github/workflows/doc-audit.yml`
   (GitHub creates the folders automatically as you type the `/` characters)
3. Paste the following:

```yaml
name: Doc Coverage Audit

on:
  pull_request:
    types: [closed]

permissions:
  pull-requests: write
  issues: write

jobs:
  audit-docs:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Get PR diff
        run: |
          git diff ${{ github.event.pull_request.base.sha }}...${{ github.event.pull_request.head.sha }} \
            --unified=5 > pr_diff.txt

      - name: Install dependencies
        run: pip install requests

      - name: Run doc audit via Claude
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          DOC360_API_KEY: ${{ secrets.DOC360_API_KEY }}
          PR_TITLE: ${{ github.event.pull_request.title }}
          PR_BODY: ${{ github.event.pull_request.body }}
        run: python scripts/doc_audit.py

      - name: Post findings to PR
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const findings = fs.readFileSync('audit_findings.md', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: findings
            });
```

4. Click **Commit changes > Commit directly to main**

---

### Phase 4 — Create the audit script

1. Click **Add file > Create new file**
2. In the filename field, type: `scripts/doc_audit.py`
3. Paste the following:

```python
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
```

4. Click **Commit changes > Commit directly to main**

---

### Phase 5 — Verify the file structure

In the GitHub file browser, confirm you see:

```
your-repo/
├── .github/
│   └── workflows/
│       └── doc-audit.yml
└── scripts/
    └── doc_audit.py
```

Click into each file and confirm it contains code, not an empty file. An empty file is the most common reason the pipeline fails silently.

---

### Phase 6 — Run a test

1. Create a new branch (e.g. `test-doc-audit`) from the branch dropdown on the main page
2. Add a file on that branch — `scripts/test_feature.py` works well:

```python
# New feature: SCIM provisioning endpoint
def provision_user(email, role, tenant_id):
    '''Create a new user via SCIM protocol'''
    pass

def deprovision_user(user_id):
    '''Remove user access when deprovisioned in Okta'''
    pass
```

3. Open a pull request from that branch with a descriptive title (e.g. `Add SCIM provisioning endpoint for Okta`)
4. Merge the PR
5. Go to **Actions** tab — you will see the `Doc Coverage Audit` workflow running
6. Once it completes (green tick), go back to the merged PR and scroll to the bottom — the bot will have posted the audit findings

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No such file or directory: scripts/doc_audit.py` | Script file is missing or empty | Open `scripts/doc_audit.py` and confirm it contains the full script from Phase 4 |
| `No event triggers defined in on` | GitHub validated the workflow on a direct push, not a PR merge | False alarm — can be ignored. The workflow is configured correctly |
| `HttpError: Resource not accessible by integration` | GitHub Actions lacks permission to post PR comments | Settings > Actions > General > Workflow permissions > Read and write permissions |
| `Claude API error: KeyError content` | Invalid API key or wrong model name | Confirm `ANTHROPIC_API_KEY` is saved correctly. Confirm the model is `claude-sonnet-4-6` |
| `No code changes detected` | Diff captured nothing — usually because only README was modified, or branch names were used instead of commit SHAs | Confirm the workflow uses `base.sha` and `head.sha`. Add a real code file to the test PR |
| `yaml syntax error on line N` | Incorrect YAML indentation | Open `doc-audit.yml`, select all, delete, and paste the workflow block from Phase 3 fresh |

---

## What the Pipeline Does Not Do

- Does not write or publish documentation automatically — it surfaces gaps for the writer to act on
- Does not modify any articles in Doc360 — it reads only
- Does not block or delay PR merges — it runs after the merge is complete
- Does not access production systems or customer data

---

## Planned Improvements

- **Diff filtering** — exclude test files, migrations, and internal utilities so Claude only analyzes user-facing code changes
- **Slack notifications** — post the audit summary to a `#docs-signals` channel automatically

---

## Author

Built by Vaishnavi Jai, a Senior Technical Writer at [Scrut Automation](https://www.scrut.io), to reduce the gap between engineering velocity and documentation coverage.
