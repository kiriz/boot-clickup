# Personal Life OS — Structure & Design Guide

This document explains the architecture of the ClickUp Personal Life OS: why each space exists, what belongs where, how the morning review workflow runs, and how to extend the system as your life evolves.

---

## Design Principles

**1. Everything has exactly one home.**  
A task that belongs in two places belongs in neither. When you're uncertain where something goes, ask: "what context will I use when I work on this?" That's the space it belongs in.

**2. Capture fast, triage later.**  
INBOX exists so you never have to make a placement decision in the moment. Drop everything there. Triage during your weekly review or TRIAGE session, not at capture time.

**3. Work at the Folder level, not the List level.**  
When you want to see a project's full picture — Gantt, all tasks, due dates, progress — open the Folder. When you want to work on today's tasks in one context, open the List. This is the single most important navigation rule.

**4. Numbered lists = sequence.**  
Lists inside folders are numbered (01, 02, 03) when order matters — client engagements, INBOX review order. Flat spaces (HEALTH, LEARNING) don't need numbers because their lists aren't sequential.

**5. Three columns on every work list.**  
Every list where you track actual work has: Start Date, % Completed, and the native Status column. This gives you scheduling, progress tracking, and state without column sprawl.

**6. Zero-miss items get special treatment.**  
FAMILY → KIDS EVENTS is the first thing you check every morning, before email, before everything else. It sits at the top of the Favorites bar for a reason.

---

## The 9 Spaces

### 1. INBOX `#87909E` — Capture Everything

**Purpose:** The universal capture bucket. Everything lands here before it has a home.

**Why it exists:** Without a capture layer, every incoming task forces an immediate routing decision. That context-switching cost is real. INBOX lets you say "I'll deal with this later" and mean it.

**Morning review order:**
- `01 TODAY` — what you committed to doing today
- `02 THIS WEEK` — what's on deck for the current week
- `03 TRIAGE` — new captures that haven't been sorted yet
- `04 SOMEDAY MAYBE` — ideas and tasks with no timeline

**Rule:** Nothing lives in TRIAGE permanently. Process it weekly. Move to another space, schedule it, or archive it.

---

### 2. WORK `#0075FF` — Professional Work

**Purpose:** All paid, client, and consulting work.

**Structure:**
```
WORK/
├── ACTIVE ENGAGEMENTS/     ← Folder (open here for full Gantt)
│   ├── 01 Client Name      ← List per client
│   ├── 02 Client Name
│   └── ...
├── INTERNAL/
│   └── Personal Ops        ← Admin, invoices, proposals, overhead
└── RECURRING/
    └── Weekly Recurring    ← Standing meetings, weekly processes
```

**Why per-client lists:** Each client engagement is its own Gantt timeline. If all clients shared one list, you'd have no way to see one client's project arc without noise from others. When an engagement ends, archive the list — clean separation.

**Naming convention:** `01 Company Name` — the number reflects priority/recency. Your most active or strategic engagement is 01. Move numbers around as priorities shift.

**Columns:** Start Date + % Completed on every list. Use % Completed to run weekly status reports in under 2 minutes.

---

### 3. PROJECTS `#7C3AED` — Side Projects

**Purpose:** Personal side projects separate from paid work.

**The hard cap:** ACTIVE holds at most 3 projects. Before adding a 4th, move one to PARKED. This isn't arbitrary — 3 is the realistic maximum for making meaningful progress while managing a full professional life. More than 3 means all of them slow down.

**Structure:**
```
PROJECTS/
├── ACTIVE       ← Max 3. Has Gantt + Table views.
├── PARKED       ← Deprioritized but not abandoned
├── IDEAS        ← Not yet committed to. No task decomposition yet.
└── ARCHIVE      ← Shipped, killed, or handed off
```

**Statuses:** Idea → Scoping → Building → Testing → Shipped / Killed. Projects should move through these. If something has been "Building" for 3 months, it either needs to go back to Scoping or it's actually Parked.

---

### 4. FAMILY `#FF4444` — Zero-Miss

**Purpose:** Family logistics, kids events, and recurring family commitments.

**Zero-miss status:** KIDS EVENTS is the highest-priority list in the entire system. A missed kids' event is the worst outcome — no work task justifies it. It sits at position 1 in the Favorites bar.

**Structure:**
```
FAMILY/
├── KIDS EVENTS          ← Check FIRST every morning
├── FAMILY TODO          ← Shared household tasks, family projects
└── RECURRING FAMILY     ← Regular commitments, routines
```

**Recommended automation (Unlimited plan):** Task created in KIDS EVENTS → set priority = Urgent. This makes KIDS EVENTS tasks visually distinct from everything else.

---

### 5. HEALTH `#22C55E` — Physical Performance

**Purpose:** Training, sports, and wellness tracking.

**Customize this space to your actual life.** The list names are placeholders — rename them to match what you actually do.

```
Defaults → What to rename to:
TRAINING  → 10K TRAINING, CYCLING, MARATHON TRAINING, CROSSFIT
SPORTS    → PICKLEBALL, TENNIS, BASKETBALL
WELLNESS  → Keep as-is, or rename to RECOVERY or SLEEP
```

**Statuses:** Planned → Done / Skipped / Modified. Modify (not skip) when you complete a scaled version of the planned workout. Tracking "what actually happened" matters more than a binary done/not-done.

---

### 6. LEARNING `#EAB308` — Knowledge Pipeline

**Purpose:** The systematic input pipeline for all long-form learning.

**Why it exists separately from INBOX:** Learning materials have a different lifecycle than tasks. A book has TBR → In Progress → Done → Applied. That progression needs its own space so it doesn't get lost in task noise.

```
LEARNING/
├── BOOKS           ← Reading queue
├── PODCASTS        ← Episodes and series worth tracking
├── DAILY TECH FEED ← Current events, tech reading, newsletters
└── COURSES         ← Structured learning with milestones
```

**Applied status:** When you apply something you learned — shipped a feature using a technique from a book, made a decision based on a podcast insight — move it to Applied and add a note. This closes the learning loop.

**Work-tracking columns:** BOOKS and COURSES get Start Date + % Completed so you can see how far into a book or course you are and set completion targets.

---

### 7. CAREER `#14B8A6` — Job Search Pipeline + Long-term Growth

**Purpose:** Active job search management and career development separate from current work.

**Why separated from WORK:** Job searching while employed requires discretion and its own mental context. Mixing job applications with client deliverables creates the wrong associations. CAREER is its own space with its own mental mode.

```
CAREER/
├── JOB PIPELINE/               ← Folder (open for pipeline Gantt)
│   ├── ACTIVE APPLICATIONS     ← Has custom fields (see below)
│   └── JD ARCHIVE              ← Rejected, withdrew, expired
└── GROWTH/
    ├── SKILLS DEVELOPMENT      ← Deliberate skill building
    ├── NETWORKING              ← Relationship tracking
    ├── OPPORTUNITIES           ← Non-application opportunities worth watching
    └── REFLECTIONS             ← Career direction, retrospectives
```

**Custom fields on ACTIVE APPLICATIONS:**
- `Job Posting URL` (url) — link to the job post before it disappears
- `Point of Contact` (text) — recruiter or hiring manager name
- `Application Type` (dropdown) — Cold / Referral / Recruiter Outreach
- `Compensation Target` (number) — your target, not their range

**Pipeline statuses:** Applied → Recruiter Screen → Technical Interview → Panel Interview → Offer → Rejected / Withdrew.

**Recommended automation:** Status = Rejected → move to JD ARCHIVE automatically. Keeps ACTIVE APPLICATIONS clean without manual archiving.

---

### 8. HOME `#F97316` — Home Management

**Purpose:** Property maintenance, seasonal tasks, and home improvement projects.

```
HOME/
├── SEASONAL CALENDAR    ← Pre-populated recurring maintenance tasks
├── HOME PROJECTS        ← Improvements, renovations, one-off projects
└── MAINTENANCE          ← Repairs, service calls, inspections
```

**SEASONAL CALENDAR** is pre-populated by `setup.py` with 8 recurring tasks derived from `seasonal_tasks` in `config.yaml`. Edit that list in the config to match your actual home — if you don't have a lawn, remove the fertilizer tasks; if you have a pool, add pool opening/closing.

**Recurrence options:** annual | biannual | quarterly | monthly

---

### 9. PERSONAL `#EC4899` — Life and Leisure

**Purpose:** Everything that doesn't fit elsewhere but still deserves to be tracked.

```
PERSONAL/
├── GAMES    ← Games backlog, gaming commitments
├── SOCIAL   ← Social commitments, events, gatherings
└── MISC     ← Everything else
```

**Low ceremony.** This is the one space where you can be loose about structure. The goal is that nothing falls through the cracks — a game you wanted to try, a friend you need to respond to, a random task that doesn't fit anywhere.

---

## The Morning Review Workflow

This workflow runs in under 15 minutes when the system is healthy.

**Order is non-negotiable.** The sequence is designed around what's catastrophic-if-missed (top) vs. what's important-but-recoverable (lower).

```
1. FAMILY → KIDS EVENTS          ← 2 min. Any events today or this week?
2. HOME → SEASONAL CALENDAR      ← 1 min. Any seasonal triggers this week?
3. INBOX → 01 TODAY              ← 5 min. What did I commit to today?
4. WORK → ACTIVE ENGAGEMENTS     ← 3 min. Folder view — any blockers?
5. PROJECTS → ACTIVE             ← 2 min. Project status check
6. CAREER → ACTIVE APPLICATIONS  ← 2 min. Anything to follow up on?
```

**Set these as Favorites** in this order. Favorites can't be set via API — do it manually once.

---

## Column Configuration

Every work-tracking list has these columns:

| Column | Type | Purpose |
|--------|------|---------|
| Name | native | Task name |
| Assignee | native | Owner |
| Start Date | custom (date) | When work begins — required for Gantt |
| Due Date | native | Deadline |
| Status | native | Current state |
| % Completed | custom (number) | Progress 0-100 |

**Priority column is hidden.** Use due date ordering for urgency instead. Priority as a separate field creates maintenance overhead and usually just duplicates what due dates already express.

---

## How to Extend the System

### Adding a new client engagement

```bash
# Create a numbered list under WORK → ACTIVE ENGAGEMENTS
curl -s -X POST https://api.clickup.com/api/v2/folder/YOUR_ACTIVE_ENGAGEMENTS_FOLDER_ID/list \
  -H "Authorization: $CLICKUP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "01 Client Name"}'
```

Then apply the column template (WORK/Personal Ops → right-click → Save as Template, then apply to new list).

### Adding a new space

1. Add the space definition to `config.yaml` under `spaces:`
2. Add any work-tracking lists to `work_tracking_lists:` in config
3. Re-running `setup.py` will create the new space but won't duplicate existing ones — it doesn't check for existing spaces, so run it against a fresh workspace only

For adding to an existing workspace, use the ClickUp API directly or the MCP tools.

### Adding custom fields to a space

Add to `job_pipeline_fields` in `config.yaml` (currently only affects CAREER/ACTIVE APPLICATIONS), or add similar field sections for other spaces and update `setup.py` to read them.

### Changing space colors

Edit the `color:` field in `config.yaml`. Accepts hex codes. A good palette: https://coolors.co

---

## What Can't Be Configured via API

These require manual setup in the ClickUp UI (~20 minutes, one time):

| Action | Where in UI |
|--------|-------------|
| Add to Favorites bar | Click star next to any folder or list |
| Save a list as Template | Right-click list → Save as Template |
| Apply a template to new list | Right-click list → Templates → Apply |
| Set Gantt to hide weekends | Any Gantt view → gear icon → uncheck "Show weekends" |
| Create Automations | Space → Automations → + New Automation |

**Recommended automations:**
- FAMILY / KIDS EVENTS: task created → set priority = Urgent
- CAREER / ACTIVE APPLICATIONS: status = Rejected → move to JD ARCHIVE
- PROJECTS / ACTIVE: status = Shipped → move to ARCHIVE
- INBOX / 03 TRIAGE: task created → assign to me

---

## File Reference

| File | Purpose |
|------|---------|
| `config.yaml` | The one file you edit to customize everything |
| `setup.py` | Reads config and builds the entire workspace via ClickUp API |
| `clickup_ids.yaml` | Generated after setup — maps space/folder/list names to IDs |
| `STRUCTURE.md` | This file — architecture and design rationale |
| `README.md` | Getting started guide |
