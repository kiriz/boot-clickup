# boot-clickup

Build a complete Personal Life OS in ClickUp from a single config file.

One command creates 9 spaces, all folders and lists, custom columns on every work-tracking list, a job search pipeline with custom fields, and a pre-populated seasonal home maintenance calendar.

---

## What gets built

| Space | Color | What it tracks |
|-------|-------|---------------|
| INBOX | Gray | Universal capture — everything lands here first |
| WORK | Blue | Client engagements, internal ops, recurring work |
| PROJECTS | Purple | Side projects — hard cap of 3 active at once |
| FAMILY | Red | Kids events (zero-miss), family todo, recurring commitments |
| HEALTH | Green | Training, sports, wellness |
| LEARNING | Yellow | Books, podcasts, courses, daily tech feed |
| CAREER | Teal | Job search pipeline + long-term career development |
| HOME | Orange | Seasonal calendar, home projects, maintenance |
| PERSONAL | Pink | Games, social, misc |

Every work-tracking list gets Start Date and % Completed columns. The CAREER / ACTIVE APPLICATIONS list gets a full job pipeline with URL, contact, application type, and compensation target fields.

---

## Prerequisites

- Python 3.8+
- PyYAML: `pip install pyyaml` (or `uv pip install pyyaml`)
- Your ClickUp Personal API Token
- A ClickUp workspace on the **Unlimited plan or higher**

**Plan requirement:** ClickUp plans are **per workspace**, not per account. A newly created workspace starts on the Free plan (5-space limit) even if you have an Unlimited subscription on another workspace. The workspace you target with `--workspace` must be on Unlimited to support all 9 spaces. Upgrade at: ClickUp → Settings → Billing.

**Get your API token:**  
ClickUp → avatar (bottom-left) → Settings → Apps → API Token

---

## Quick start

```bash
git clone https://github.com/kiriz/boot-clickup.git
cd boot-clickup

pip install pyyaml

export CLICKUP_API_KEY=pk_xxxxx
python setup.py --workspace "Your Workspace Name"
```

That's it. The script prints progress as it creates each space, folder, and list. When it finishes, `clickup_ids.yaml` has the ID of every created entity.

---

## Preview before running

Run a dry run to see every API call without making any changes:

```bash
python setup.py --dry-run
```

All API calls are printed. No changes are made to your ClickUp workspace.

---

## Customization

Open `config.yaml` and edit it before running. Everything is in there:

```yaml
spaces:
  inbox:
    name: "INBOX"           # rename to anything
    color: "#87909E"        # any hex color
    lists:
      today:
        name: "01 TODAY"    # rename lists too
```

**Common customizations:**

- **Rename HEALTH lists** to match your actual activities:  
  `TRAINING → 10K TRAINING`, `SPORTS → PICKLEBALL`

- **Add seasonal maintenance tasks** to HOME / SEASONAL CALENDAR:
  ```yaml
  seasonal_tasks:
    - name: "Pool opening"
      month: 5
      recurrence: annual
  ```

- **Remove spaces** if you're on ClickUp Free (5-space limit):  
  Delete the space entry from `config.yaml`

- **Change job pipeline dropdown options:**
  ```yaml
  job_pipeline_fields:
    - name: "Application Type"
      type: drop_down
      options: [Cold, Referral, Recruiter Outreach, Internal]
  ```

See `STRUCTURE.md` for a full explanation of every design decision.

---

## CLI options

```
python setup.py [options]

Options:
  --api-key, -k      ClickUp personal API token (or set CLICKUP_API_KEY env var)
  --workspace, -w    Target workspace name (required if you belong to multiple workspaces)
  --config, -c       Path to config YAML file (default: config.yaml)
  --dry-run          Print all API calls without executing them
  --output, -o       Output file for generated IDs (default: clickup_ids.yaml)

Examples:
  python setup.py --workspace "My Workspace"                # full setup
  python setup.py --dry-run                                 # preview only
  python setup.py --workspace "My Workspace" --dry-run      # preview targeting specific workspace
  python setup.py --config my_config.yaml                   # custom config file
  python setup.py --output my_workspace_ids.yaml            # custom output path
```

---

## After setup — manual steps (~20 min)

A few things can't be set via API and require the ClickUp UI:

**1. Add Favorites** (in this order for the morning review workflow):
- FAMILY → KIDS EVENTS
- HOME → SEASONAL CALENDAR
- INBOX → 01 TODAY
- WORK → ACTIVE ENGAGEMENTS
- PROJECTS → ACTIVE
- CAREER → ACTIVE APPLICATIONS

**2. Save a list template:**  
Open WORK / Personal Ops → right-click → Save as Template → name it "Standard Work List"  
Use this template when creating new client engagement lists

**3. Gantt settings:**  
Open any Gantt view → gear icon → uncheck "Show weekends"

**4. Automations** (Unlimited plan):
- FAMILY / KIDS EVENTS: task created → set priority = Urgent
- CAREER / ACTIVE APPLICATIONS: status = Rejected → move to JD ARCHIVE
- PROJECTS / ACTIVE: status = Shipped → move to ARCHIVE

---

## Architecture

See `STRUCTURE.md` for:
- Why each space exists and what belongs in it
- The morning review workflow
- Navigation rule (Folder vs List level)
- Column configuration rationale
- How to extend the system as your life evolves
- What can and can't be configured via API

---

## License

MIT
