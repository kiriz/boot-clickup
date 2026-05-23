#!/usr/bin/env python3
"""
setup_ui.py — Automates the 4 ClickUp manual UI steps using the interceptor CLI.

Steps (in order):
  1. Favorites bar — add 6 items in morning-review order
  2. List template — save WORK / Personal Ops as "PAI Standard Work List"
  3. Gantt settings — hide weekends in WORK / ACTIVE ENGAGEMENTS gantt
  4. Automations — create 4 automation rules

Requirements:
  - Chrome running with Interceptor extension loaded
  - `interceptor` binary in PATH (~/Projects/tools/ai-dev-tools/interceptor/dist/)
  - ClickUp already logged in in Chrome

Usage:
  python setup_ui.py
  python setup_ui.py --dry-run   # print actions without executing them
  python setup_ui.py --step favorites|template|gantt|automations  # run one step only
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Interceptor binary resolution
# ---------------------------------------------------------------------------

_INTERCEPTOR_FALLBACK = os.path.expanduser(
    "~/Projects/tools/ai-dev-tools/interceptor/dist/interceptor"
)

def _resolve_interceptor() -> str:
    """Return the interceptor binary path, searching PATH then the known install location."""
    found = shutil.which("interceptor")
    if found:
        return found
    if os.path.isfile(_INTERCEPTOR_FALLBACK):
        return _INTERCEPTOR_FALLBACK
    raise FileNotFoundError(
        "interceptor binary not found.\n"
        "  Expected: ~/Projects/tools/ai-dev-tools/interceptor/dist/interceptor\n"
        "  Or add it to PATH: export PATH=\"$PATH:~/Projects/tools/ai-dev-tools/interceptor/dist\""
    )

INTERCEPTOR_BIN = None  # resolved in main() after arg parsing

# ---------------------------------------------------------------------------
# Workspace constants (from ~/.claude/PAI/USER/CLICKUP.yaml)
# ---------------------------------------------------------------------------

WORKSPACE_ID = "90141166201"
BASE_URL = f"https://app.clickup.com/{WORKSPACE_ID}"

LIST_IDS = {
    "kids_events":        "901416671374",   # FAMILY → KIDS EVENTS
    "seasonal_calendar":  "901416671390",   # HOME → SEASONAL CALENDAR
    "today":              "901416671358",   # INBOX → 01 TODAY
    "active":             "901416671366",   # PROJECTS → ACTIVE
    "active_applications":"901416671384",   # CAREER → ACTIVE APPLICATIONS
    "personal_ops":       "901416671363",   # WORK → Personal Ops
    "triage":             "901416671360",   # INBOX → 03 TRIAGE
    "jd_archive":         "901416671385",   # CAREER → JD ARCHIVE
    "archive":            "901416671369",   # PROJECTS → ARCHIVE
}

FOLDER_IDS = {
    "active_engagements": "90149582395",   # WORK → ACTIVE ENGAGEMENTS
}

SPACE_IDS = {
    "family":   "90145748236",
    "career":   "90145748441",
    "projects": "90145748235",
    "inbox":    "90145748233",
}

# ---------------------------------------------------------------------------
# Interceptor wrapper
# ---------------------------------------------------------------------------

DRY_RUN = False


def interceptor(*args, wait_after=800, require_ok=False) -> dict:
    """Run an interceptor command. Returns parsed JSON or empty dict on failure."""
    cmd = [INTERCEPTOR_BIN] + list(args) + ["--json"]
    if DRY_RUN:
        print(f"    [dry-run] interceptor {' '.join(str(a) for a in args)}")
        return {"status": "ok"}
    result = subprocess.run(cmd, capture_output=True, text=True)
    if wait_after:
        time.sleep(wait_after / 1000)
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()
        print(f"    ✗ interceptor {args[0]}: {msg[:120]}")
        if require_ok:
            raise RuntimeError(f"Command failed: {cmd}")
        return {}
    try:
        data = json.loads(result.stdout)
        return data if isinstance(data, dict) else {"result": data}
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}


def navigate(url: str, wait_ms=2500) -> dict:
    """Open URL and wait for it to stabilise."""
    print(f"  → navigating to {url}")
    result = interceptor("open", url, "--no-wait")
    time.sleep(wait_ms / 1000)
    return result


def screenshot(label: str) -> None:
    """Capture a screenshot to confirm the current state."""
    if DRY_RUN:
        print(f"    [dry-run] screenshot: {label}")
        return
    result = subprocess.run(
        [INTERCEPTOR_BIN, "screenshot", "--save"],
        capture_output=True, text=True
    )
    path = result.stdout.strip().split("\n")[-1] if result.stdout else "(unknown)"
    print(f"    📸 screenshot saved: {path}  [{label}]")


def find_ref(query: str, role: Optional[str] = None) -> Optional[str]:
    """Find an element by text query, return its ref (eN) or None."""
    if DRY_RUN:
        return "e99"
    args = ["find", query]
    if role:
        args += ["--role", role]
    data = interceptor(*args, wait_after=0)
    results = data.get("results") or data.get("result") or []
    if isinstance(results, list) and results:
        return results[0].get("ref") or results[0].get("index")
    return None


def wait_stable(ms: int = 1500) -> None:
    interceptor("wait-stable", "--ms", str(ms), wait_after=0)


# ---------------------------------------------------------------------------
# Step 1 — Favorites
# ---------------------------------------------------------------------------

FAVORITES = [
    ("FAMILY → KIDS EVENTS",           "list",   LIST_IDS["kids_events"]),
    ("HOME → SEASONAL CALENDAR",        "list",   LIST_IDS["seasonal_calendar"]),
    ("INBOX → 01 TODAY",                "list",   LIST_IDS["today"]),
    ("WORK → ACTIVE ENGAGEMENTS",       "folder", FOLDER_IDS["active_engagements"]),
    ("PROJECTS → ACTIVE",               "list",   LIST_IDS["active"]),
    ("CAREER → ACTIVE APPLICATIONS",    "list",   LIST_IDS["active_applications"]),
]


def _list_url(list_id: str) -> str:
    # ClickUp 3.0 URL format: /v/l/li/{list_id}  (note: "li" prefix required)
    return f"{BASE_URL}/v/l/li/{list_id}"


def _folder_url(folder_id: str) -> str:
    # ClickUp 3.0 folder URL — discovered empirically to require /v/f/li/ prefix
    return f"{BASE_URL}/v/f/li/{folder_id}"


def _entity_url(entity_type: str, entity_id: str) -> str:
    if entity_type == "list":
        return _list_url(entity_id)
    return _folder_url(entity_id)


def _js_eval(code: str) -> str:
    """Run JS via eval --main, strip CSP noise, return the value string."""
    if DRY_RUN:
        return "dry-run"
    result = subprocess.run(
        [INTERCEPTOR_BIN, "eval", code, "--main"],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)
        val = data.get("value", "")
        return str(val) if val is not None else ""
    except (json.JSONDecodeError, AttributeError):
        return ""


def _is_already_favorite() -> bool:
    """
    Check if the currently-open list/folder is already in the Favorites sidebar section.
    Opens the star dropdown and checks if the 'Favorites' menu item has 'menu-item-selected'.
    Closes the dropdown afterwards.
    """
    # Open the star dropdown by dispatching full mouse event sequence
    code = r"""
var btn = document.querySelector('.button.favorited.cu-dropdown__toggle') ||
          document.querySelector('.button.cu-dropdown__toggle');
if (!btn) { JSON.stringify({found: false}); }
else {
  var rect = btn.getBoundingClientRect();
  var cx = rect.left + rect.width/2, cy = rect.top + rect.height/2;
  ['mouseenter','mouseover','mousedown','mouseup','click'].forEach(function(t) {
    btn.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, clientX:cx, clientY:cy, view:window}));
  });
  JSON.stringify({found: true, cls: btn.className});
}
"""
    result = _js_eval(code)
    if '"found":false' in result:
        return False
    time.sleep(0.8)

    check = r"""
var overlay = document.querySelector('.cdk-overlay-container');
var items = Array.from(overlay ? overlay.querySelectorAll('[class*="menu-item"], .cdk-menu-item') : []);
var favItem = items.find(function(i) { return i.textContent.trim() === 'Favorites'; });
JSON.stringify({
  found: !!favItem,
  selected: favItem ? favItem.className.indexOf('menu-item-selected') >= 0 : false,
  cls: favItem ? favItem.className : ''
})
"""
    check_result = _js_eval(check)

    # Close the dropdown
    subprocess.run([INTERCEPTOR_BIN, "keys", "Escape", "--json"],
                   capture_output=True, text=True)
    time.sleep(0.3)

    return '"selected":true' in check_result


def _add_to_favorites_via_dropdown() -> bool:
    """
    Open the star dropdown and click the 'Favorites' section option.
    Returns True if successfully added, False otherwise.
    """
    # Open dropdown
    code = r"""
var btn = document.querySelector('.button.favorited.cu-dropdown__toggle') ||
          document.querySelector('.button.cu-dropdown__toggle');
if (!btn) { 'not-found'; }
else {
  var rect = btn.getBoundingClientRect();
  var cx = rect.left + rect.width/2, cy = rect.top + rect.height/2;
  ['mouseenter','mouseover','mousedown','mouseup','click'].forEach(function(t) {
    btn.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, clientX:cx, clientY:cy, view:window}));
  });
  'ok';
}
"""
    result = _js_eval(code)
    if "not-found" in result:
        return False
    time.sleep(0.8)

    # Click the 'Favorites' menu item
    click_code = r"""
var overlay = document.querySelector('.cdk-overlay-container');
var items = Array.from(overlay ? overlay.querySelectorAll('[class*="menu-item"], .cdk-menu-item') : []);
var favItem = items.find(function(i) { return i.textContent.trim() === 'Favorites'; });
if (favItem) {
  favItem.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
  'clicked:' + favItem.className;
} else { 'not-found'; }
"""
    click_result = _js_eval(click_code)
    time.sleep(0.5)
    return "clicked:" in click_result


def step_favorites() -> None:
    print("\n── STEP 1: Favorites bar ──────────────────────────────────────")
    ok = 0
    already = 0
    for name, entity_type, entity_id in FAVORITES:
        print(f"  {name}")
        navigate(_entity_url(entity_type, entity_id), wait_ms=3500)
        wait_stable(1500)

        if DRY_RUN:
            print(f"    ✓ [dry-run] would add to favorites")
            ok += 1
            continue

        if _is_already_favorite():
            print(f"    ✓ already in Favorites")
            already += 1
            ok += 1
        elif _add_to_favorites_via_dropdown():
            print(f"    ✓ added to Favorites")
            ok += 1
        else:
            print(f"    ✗ could not add — check Chrome manually")

    print(f"\n  Result: {ok}/{len(FAVORITES)} items in Favorites ({already} were already set)")


# ---------------------------------------------------------------------------
# Step 2 — Save list template
# ---------------------------------------------------------------------------

def step_template() -> None:
    print("\n── STEP 2: Save list template ─────────────────────────────────")
    template_name = "PAI Standard Work List"
    list_id = LIST_IDS["personal_ops"]

    navigate(_list_url(list_id), wait_ms=3500)
    wait_stable(1500)

    # Right-click the list name in the sidebar to get context menu
    # ClickUp sidebar items typically have the list name as text + a "..." button on hover
    # Strategy: find the "..." (more options) button for the list and click it
    print(f"  looking for list options menu...")
    ref = find_ref("Personal Ops")
    if ref:
        # Right-click to open context menu
        interceptor("rightclick", ref, wait_after=800)
        # Look for "Save as Template" in the context menu
        tmpl_ref = find_ref("Save as Template")
        if tmpl_ref:
            interceptor("act", tmpl_ref, wait_after=1000)
            # Template name dialog — type the name
            name_ref = find_ref("Template name", role="textbox") or find_ref("Name", role="textbox")
            if not name_ref:
                # Try finding any visible input
                name_ref = find_ref(template_name, role="textbox")
            if name_ref:
                interceptor("type", name_ref, template_name, wait_after=500)
            # Click Save
            save_ref = find_ref("Save", role="button") or find_ref("Create", role="button")
            if save_ref:
                interceptor("act", save_ref, wait_after=1000)
                print(f"  ✓ template '{template_name}' saved")
                screenshot("template-saved")
                return
    print(f"  ✗ could not automate template save")
    print(f"    Manual step: WORK → Personal Ops → right-click → Save as Template → '{template_name}'")
    screenshot("template-fail")


# ---------------------------------------------------------------------------
# Step 3 — Gantt hide weekends
# ---------------------------------------------------------------------------

def step_gantt() -> None:
    print("\n── STEP 3: Gantt — hide weekends ──────────────────────────────")
    folder_id = FOLDER_IDS["active_engagements"]

    # Navigate to the folder, then switch to Gantt view
    navigate(_folder_url(folder_id), wait_ms=3500)
    wait_stable(1500)

    # Look for Gantt view tab in the view switcher
    gantt_ref = find_ref("Gantt", role="tab") or find_ref("Gantt")
    if gantt_ref:
        interceptor("act", gantt_ref, wait_after=2000)
        wait_stable(2000)
    else:
        # Try navigating directly to gantt URL (ClickUp supports ?view=gantt in some versions)
        navigate(f"{_folder_url(folder_id)}?view=gantt", wait_ms=3000)

    screenshot("gantt-opened")

    # Click the Settings/gear icon in the Gantt toolbar
    settings_ref = (
        find_ref("Settings", role="button")
        or find_ref("Gantt Settings")
        or find_ref("settings")
    )
    if settings_ref:
        interceptor("act", settings_ref, wait_after=1000)
        # Find and uncheck "Show weekends"
        weekends_ref = find_ref("Show weekends") or find_ref("Weekends")
        if weekends_ref:
            # Check if it's currently checked; if so, click to uncheck
            data = interceptor("html", weekends_ref, wait_after=0)
            html = data.get("html") or data.get("raw") or ""
            if 'checked' in html.lower() or 'true' in html.lower():
                interceptor("act", weekends_ref, wait_after=500)
                print("  ✓ weekends hidden in Gantt")
                screenshot("gantt-weekends-hidden")
                return
            else:
                # Checkbox may not be checked — just click to toggle
                interceptor("act", weekends_ref, wait_after=500)
                print("  ✓ weekends toggle clicked")
                screenshot("gantt-weekends-toggled")
                return

    print("  ✗ could not locate Gantt settings — please hide weekends manually")
    print("    Manual step: WORK → ACTIVE ENGAGEMENTS → Gantt view → gear icon → uncheck 'Show weekends'")
    screenshot("gantt-settings-fail")


# ---------------------------------------------------------------------------
# Step 4 — Automations
# ---------------------------------------------------------------------------

AUTOMATIONS = [
    {
        "name": "FAMILY / KIDS EVENTS — new task → Urgent",
        "space": "family",
        "url": f"{BASE_URL}/automations/{SPACE_IDS['family']}",
        "description": "Trigger: Task created  |  Action: Set priority → Urgent",
    },
    {
        "name": "CAREER / ACTIVE APPLICATIONS — Rejected → move to JD ARCHIVE",
        "space": "career",
        "url": f"{BASE_URL}/automations/{SPACE_IDS['career']}",
        "description": "Trigger: Status changes to Rejected  |  Action: Move task → JD ARCHIVE",
    },
    {
        "name": "PROJECTS / ACTIVE — Shipped → move to ARCHIVE",
        "space": "projects",
        "url": f"{BASE_URL}/automations/{SPACE_IDS['projects']}",
        "description": "Trigger: Status changes to Shipped  |  Action: Move task → ARCHIVE",
    },
    {
        "name": "INBOX / 03 TRIAGE — new task → assign to me",
        "space": "inbox",
        "url": f"{BASE_URL}/automations/{SPACE_IDS['inbox']}",
        "description": "Trigger: Task created  |  Action: Assign task → me",
    },
]


def _create_automation_ui(automation: dict) -> bool:
    """
    Navigate to the automation center for this space and create one automation.
    ClickUp's automation builder is a heavily interactive modal — this attempts
    the common flow but may need manual completion for complex rules.
    """
    navigate(automation["url"], wait_ms=3000)
    wait_stable()

    # Click "New Automation" or "Create Automation" button
    new_ref = (
        find_ref("New Automation", role="button")
        or find_ref("Create Automation", role="button")
        or find_ref("Add Automation", role="button")
    )
    if not new_ref:
        # Some ClickUp versions show a "+" button
        new_ref = find_ref("automation")
        if not new_ref:
            return False

    interceptor("act", new_ref, wait_after=1500)
    screenshot(f"automation-builder-{automation['space']}")
    # The automation builder is deeply interactive (choose trigger → choose action → configure)
    # Return False here to signal that manual completion is needed
    return False


def step_automations() -> None:
    print("\n── STEP 4: Automations ────────────────────────────────────────")
    print("  Note: ClickUp's automation builder requires interactive multi-step")
    print("  configuration. This step navigates to each space's automation center")
    print("  and opens the builder. You complete the trigger + action selection.")
    print()

    for automation in AUTOMATIONS:
        print(f"  {automation['name']}")
        print(f"    {automation['description']}")
        result = _create_automation_ui(automation)
        if result:
            print(f"    ✓ automation created")
        else:
            print(f"    → opened automation builder — complete manually in Chrome")
            print(f"    → URL: {automation['url']}")
        print()

    print("  Manual automation checklist (if any above need completion):")
    print()
    for a in AUTOMATIONS:
        print(f"  [ ] {a['name']}")
        print(f"      {a['description']}")
    print()
    screenshot("automations-done")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

STEPS = {
    "favorites":   step_favorites,
    "template":    step_template,
    "gantt":       step_gantt,
    "automations": step_automations,
}


def check_interceptor() -> bool:
    """Verify interceptor is reachable and Chrome is running."""
    result = subprocess.run(
        [INTERCEPTOR_BIN, "status", "--json"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
        return bool(data.get("daemon"))
    except (json.JSONDecodeError, AttributeError):
        return "daemon: running" in result.stdout


def main() -> None:
    global DRY_RUN

    parser = argparse.ArgumentParser(
        description="Automates ClickUp manual UI setup steps via interceptor."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print actions without executing them"
    )
    parser.add_argument(
        "--step", choices=list(STEPS.keys()),
        help="Run only one step (default: run all in order)"
    )
    args = parser.parse_args()

    DRY_RUN = args.dry_run

    global INTERCEPTOR_BIN
    try:
        INTERCEPTOR_BIN = _resolve_interceptor()
    except FileNotFoundError as e:
        print(f"✗ {e}")
        sys.exit(1)

    if DRY_RUN:
        print("DRY RUN — no browser actions will be taken\n")
    else:
        print("Checking interceptor + Chrome connection...")
        if not check_interceptor():
            print("✗ Could not connect to interceptor. Make sure:")
            print("  1. Chrome is running")
            print("  2. Interceptor extension is loaded (chrome://extensions)")
            print("  3. interceptor binary is in PATH")
            print("  4. interceptor-daemon is running (starts automatically on first command)")
            sys.exit(1)
        print("✓ Connected\n")

    steps_to_run = [args.step] if args.step else list(STEPS.keys())
    print(f"Running steps: {', '.join(steps_to_run)}\n")

    for step_name in steps_to_run:
        try:
            STEPS[step_name]()
        except Exception as e:
            print(f"\n✗ Step '{step_name}' failed: {e}")
            print("  Continuing with next step...\n")

    print("\n────────────────────────────────────────────────────────────────")
    print("setup_ui.py complete.")
    print()
    print("Manual steps that always require human interaction:")
    print("  • Automations: use ClickUp UI to configure trigger + action per rule")
    print("  • Gantt preferences (show/hide weekends) are per-user, not per-workspace")
    print("  • Template configuration: verify column setup before saving")


if __name__ == "__main__":
    main()
