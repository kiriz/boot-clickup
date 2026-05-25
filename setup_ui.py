#!/usr/bin/env python3
"""
setup_ui.py — Automates the 4 ClickUp manual UI steps using the interceptor CLI.

Robust Interceptor patterns used throughout:
  1. navigate_and_verify(): compound open + text verification + retry once.
     Always check the page loaded correctly before acting.
  2. Semantic finding: `interceptor find "label" --role type` locates refs by
     meaning, not CSS class. Refs change every page load; semantic names don't.
  3. act + immediate eval: After `interceptor act <ref>` opens an Angular CDK
     overlay, the ONLY safe next call is `eval --main` with synchronous JS.
     Any `interceptor tree/state/find/read` between them triggers wait_stable
     which closes the overlay. Collect all refs BEFORE opening any overlay.

Steps:
  1. favorites   — add 6 sidebar items in morning-review order
  2. template    — save WORK / Personal Ops as "PAI Standard Work List"
  3. gantt       — hide weekends in WORK / ACTIVE ENGAGEMENTS Gantt
  4. automations — guided: opens automation builder for each of 4 rules

Usage:
  python setup_ui.py
  python setup_ui.py --dry-run
  python setup_ui.py --step favorites|template|gantt|automations
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
    found = shutil.which("interceptor")
    if found:
        return found
    if os.path.isfile(_INTERCEPTOR_FALLBACK):
        return _INTERCEPTOR_FALLBACK
    raise FileNotFoundError(
        "interceptor binary not found.\n"
        "  Expected: ~/Projects/tools/ai-dev-tools/interceptor/dist/interceptor\n"
        "  Or: export PATH=\"$PATH:~/Projects/tools/ai-dev-tools/interceptor/dist\""
    )


INTERCEPTOR_BIN: Optional[str] = None  # resolved in main()

# ---------------------------------------------------------------------------
# Workspace constants (from ~/.claude/PAI/USER/CLICKUP.yaml)
# ---------------------------------------------------------------------------

WORKSPACE_ID = "90141166201"
BASE_URL = f"https://app.clickup.com/{WORKSPACE_ID}"

LIST_IDS = {
    "kids_events":         "901416671374",
    "seasonal_calendar":   "901416671390",
    "today":               "901416671358",
    "active":              "901416671366",
    "active_applications": "901416671384",
    "personal_ops":        "901416671363",
    "triage":              "901416671360",
    "jd_archive":          "901416671385",
    "archive":             "901416671369",
}

FOLDER_IDS = {
    "active_engagements": "90149582395",
}

SPACE_IDS = {
    "family":   "90145748236",
    "career":   "90145748441",
    "projects": "90145748235",
    "inbox":    "90145748233",
}

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

DRY_RUN = False


def interceptor(*args, wait_after: int = 800, require_ok: bool = False) -> dict:
    """
    Run an interceptor command with --json. Returns parsed response or {}.

    interceptor wraps results in a {success, data, tabId} envelope.
    Commands that return content (read, find, wait-stable) put it in `data`.
    Commands that just act (navigate, act, keys) return {success, tabId} with no `data`.
    `status` uses a flat {daemon, bridge} format with no envelope.

    We unwrap the envelope so callers see content directly:
      read  → {"tree": ..., "text": ...}
      find  → {"results": [...]}       (data was a list)
      act   → {"success": True}        (no data key — unchanged)
    """
    cmd = [INTERCEPTOR_BIN] + [str(a) for a in args] + ["--json"]
    if DRY_RUN:
        print(f"    [dry-run] interceptor {' '.join(str(a) for a in args)}")
        return {"status": "ok"}
    result = subprocess.run(cmd, capture_output=True, text=True)
    if wait_after:
        time.sleep(wait_after / 1000)
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()
        if require_ok:
            raise RuntimeError(f"interceptor {args[0]} failed: {msg[:120]}")
        return {"error": msg[:120]}
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}
    if not isinstance(raw, dict):
        return {"result": raw}
    # Unwrap {success, data, tabId} envelope when present
    if "success" in raw and "data" in raw:
        inner = raw["data"]
        if isinstance(inner, dict):
            return inner                    # read → {tree, text}; wait-stable → {stable,...}
        if isinstance(inner, list):
            return {"results": inner}       # find → {results: [...]}
    return raw


def _js_eval(code: str) -> str:
    """
    Run synchronous JS via `eval --main`. Returns the 'value' string.
    IMPORTANT: do NOT add --json — it breaks the browser's JSON object.
    """
    if DRY_RUN:
        return "dry-run"
    result = subprocess.run(
        [INTERCEPTOR_BIN, "eval", code, "--main"],
        capture_output=True, text=True,
        timeout=20,
    )
    try:
        data = json.loads(result.stdout)
        if "value" in data:
            # Enveloped format: {"value": "...", "cspBypassApplied": true, ...}
            val = data["value"]
            return str(val) if val is not None else ""
        # Raw format: eval returned an object directly (no envelope key)
        return result.stdout.strip()
    except (json.JSONDecodeError, AttributeError):
        return result.stdout.strip()


def _extract_refs(find_result: dict) -> list:
    """Pull the list of result entries from a find response (unwrapped by interceptor())."""
    r = find_result.get("results") or find_result.get("result") or find_result.get("data") or []
    return r if isinstance(r, list) else []


def _ref(entry: dict) -> Optional[str]:
    return entry.get("refId") or entry.get("ref") or entry.get("index")


def _page_text() -> str:
    """Read visible text from the current tab. Plain sleep avoids wait-stable daemon issue."""
    # wait-stable blocks subsequent eval --main calls — use timed sleep instead
    time.sleep(2.5)
    return interceptor("read", wait_after=400).get("text", "")


def navigate_and_verify(url: str, expected_text: str, label: str, wait_ms: int = 3500) -> bool:
    """
    Navigate the current tab to url, then verify expected_text is in page text.
    Uses `navigate` (not `open`) so no new tab is created. Retries once.
    """
    print(f"  ▸ {label}")
    interceptor("navigate", url, wait_after=wait_ms)
    text = _page_text()

    if expected_text.lower() not in text.lower():
        print(f"    ⚠ expected '{expected_text}' in page — retrying...")
        time.sleep(1.5)
        interceptor("navigate", url, wait_after=wait_ms)
        text = _page_text()
        if expected_text.lower() not in text.lower():
            print(f"    ✗ page verification failed after retry")
            return False
    return True


def screenshot(label: str) -> None:
    if DRY_RUN:
        print(f"    [dry-run] screenshot: {label}")
        return
    result = subprocess.run(
        [INTERCEPTOR_BIN, "screenshot", "--save"], capture_output=True, text=True
    )
    path = (result.stdout or "").strip().split("\n")[-1]
    print(f"    📸 {path}  [{label}]")


def _list_url(list_id: str) -> str:
    return f"{BASE_URL}/v/l/li/{list_id}"


def _folder_url(folder_id: str) -> str:
    return f"{BASE_URL}/v/f/{folder_id}"


# ---------------------------------------------------------------------------
# Step 1 — Favorites
# ---------------------------------------------------------------------------

# (name, entity_type, entity_id, verify_text)
FAVORITES = [
    ("FAMILY → KIDS EVENTS",         "list",   LIST_IDS["kids_events"],         "Kids Events"),
    ("HOME → SEASONAL CALENDAR",      "list",   LIST_IDS["seasonal_calendar"],   "Seasonal Calendar"),
    ("INBOX → 01 TODAY",              "list",   LIST_IDS["today"],               "01 TODAY"),
    ("WORK → ACTIVE ENGAGEMENTS",     "folder", FOLDER_IDS["active_engagements"],"ACTIVE ENGAGEMENTS"),
    ("PROJECTS → ACTIVE",             "list",   LIST_IDS["active"],              "ACTIVE"),
    ("CAREER → ACTIVE APPLICATIONS",  "list",   LIST_IDS["active_applications"], "ACTIVE APPLICATIONS"),
]

# Step 1: Click the "Favorite" button in the view header using JS dispatchEvent.
# interceptor click doesn't trigger Angular CDK's event listeners reliably;
# dispatching a full mouse event sequence via JS does.
_CLICK_FAVORITE_BTN_JS = r"""
(function() {
    // The view-header Favorites button has aria-label "Open Favorites menu".
    // The sidebar "Favorites" section header uses class "expand-button" — exclude it.
    var allBtns = Array.from(document.querySelectorAll('button,[role="button"]'));

    // Priority 1: aria-label contains "favorites" (the view header star button)
    var btn = allBtns.find(function(b) {
        var lbl = (b.getAttribute('aria-label') || '').toLowerCase();
        return lbl.indexOf('favorites') >= 0 && !b.classList.contains('expand-button');
    });

    // Priority 2: textContent contains "favor" but not the sidebar expand-button
    if (!btn) {
        btn = allBtns.find(function(b) {
            return b.textContent.trim().toLowerCase().indexOf('favor') >= 0
                && !b.classList.contains('expand-button');
        });
    }

    if (!btn) return JSON.stringify({error: 'no-favorite-button'});

    var ariaLabel = btn.getAttribute('aria-label') || '';
    if (ariaLabel.toLowerCase().indexOf('remove') >= 0
            || btn.getAttribute('aria-pressed') === 'true') {
        return JSON.stringify({error: 'already-favorited', label: ariaLabel.slice(0,60)});
    }

    var rect = btn.getBoundingClientRect();
    var cx = rect.left + rect.width/2, cy = rect.top + rect.height/2;
    ['mouseenter','mouseover','mousedown','mouseup','click'].forEach(function(t) {
        btn.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, clientX:cx, clientY:cy, view:window}));
    });
    return JSON.stringify({clicked: true, text: btn.textContent.trim().slice(0,40), cls: btn.className.slice(0,80), ariaLabel: ariaLabel});
})()
"""

# Step 2 (run after Python time.sleep(2.0) for Angular to render the CDK overlay):
# Check if "Favorites" section is already selected; click it if not.
# Selectors confirmed via live DOM inspection: button/[role=menuitem]/[class*=menu-item]
# finds 6 items including "Favorites" in the cu-nav-menu-move-to-section dropdown.
_FAVORITE_CHECK_JS = r"""
(function() {
    var overlay = document.querySelector('.cdk-overlay-container');
    if (!overlay) return JSON.stringify({error: 'no-overlay'});
    var items = Array.from(
        overlay.querySelectorAll('button,[role="menuitem"],[class*="menu-item"],[class*="cu3-menu-item"]')
    );
    if (!items.length) return JSON.stringify({
        error: 'no-menu-items',
        html: overlay.innerHTML.slice(0, 300)
    });
    var favItem = items.find(function(i) { return i.textContent.trim() === 'Favorites'; });
    if (!favItem) {
        return JSON.stringify({
            error: 'fav-item-not-found',
            available: items.map(function(i){ return i.textContent.trim(); }).join(' | ')
        });
    }
    var selected = favItem.className.indexOf('menu-item-selected') >= 0
                   || favItem.getAttribute('aria-checked') === 'true';
    if (selected) {
        document.body.click();
        return JSON.stringify({status: 'already_favorite'});
    }
    favItem.click();
    return JSON.stringify({status: 'added'});
})()
"""



def _favorite_action() -> str:
    """
    Detect and toggle Favorites for the currently-open list/folder.
    Returns: 'already_favorite' | 'added' | 'failed'

    Pattern:
      1. eval --main: JS dispatchEvent on the 'Favorite' button (text-match, no tree ref)
         → interceptor click doesn't trigger Angular CDK event listeners reliably
      2. time.sleep(2.0): let Angular render the CDK overlay (NOT an interceptor call)
         → overlay exists immediately after click but items render async
      3. eval --main: check 'Favorites' item in overlay, click if not already selected
         → zero interceptor reads between step 1 and step 3
    """
    # Angular takes ~10s from navigate to render the view header buttons.
    # navigate_and_verify waits ~7s total; we need ~3s more here before eval.
    time.sleep(3.0)

    # Step 1: click the Favorite button via JS event dispatch
    click_val = _js_eval(_CLICK_FAVORITE_BTN_JS)
    if '"error"' in click_val:
        try:
            info = json.loads(click_val)
            err = info.get('error', '?')
            if err == 'already-favorited':
                print(f"    ⚠ button says '{info.get('label', info.get('text',''))}' — already in Favorites")
                return "already_favorite"
            print(f"    ⚠ {err}")
        except Exception:
            print(f"    ⚠ click JS: {click_val[:80]}")
        return "failed"

    # Step 2: Python sleep (no interceptor calls) — let Angular render dropdown items
    time.sleep(2.0)

    # Step 3: check + click the Favorites section item
    val = _js_eval(_FAVORITE_CHECK_JS)
    time.sleep(0.3)

    if '"status":"already_favorite"' in val:
        return "already_favorite"
    if '"status":"added"' in val:
        return "added"

    try:
        info = json.loads(val)
        print(f"    ⚠ overlay: {info.get('error','?')} — {info.get('available', info.get('html',''))[:100]}")
    except Exception:
        print(f"    ⚠ unexpected: {repr(val[:120])}")
    return "failed"


def step_favorites() -> None:
    print("\n── STEP 1: Favorites bar ──────────────────────────────────────")
    ok = already = 0

    for name, entity_type, entity_id, verify_text in FAVORITES:
        url = _list_url(entity_id) if entity_type == "list" else _folder_url(entity_id)
        if not navigate_and_verify(url, verify_text, name, wait_ms=3500):
            print(f"    ✗ navigation failed — skipping")
            continue

        if DRY_RUN:
            print(f"    ✓ [dry-run]")
            ok += 1
            continue

        status = _favorite_action()
        if status == "already_favorite":
            print(f"    ✓ already in Favorites")
            already += 1
            ok += 1
        elif status == "added":
            print(f"    ✓ added to Favorites")
            ok += 1
            screenshot(f"fav-{entity_id}")
        else:
            print(f"    ✗ failed — add manually: hover item in sidebar → ★")

    print(f"\n  Result: {ok}/{len(FAVORITES)} in Favorites ({already} already set)")
    if ok < len(FAVORITES):
        print("  Remaining items: hover each in ClickUp sidebar → click ★")


# ---------------------------------------------------------------------------
# Step 2 — Save list template
# ---------------------------------------------------------------------------

_CONTEXTMENU_JS = r"""
(function() {
    var els = Array.from(document.querySelectorAll('*')).filter(function(el) {
        return el.childElementCount === 0 && el.textContent.trim() === 'Personal Ops';
    });
    if (!els.length) return JSON.stringify({error: 'not-found'});
    var el = els[0];
    var rect = el.getBoundingClientRect();
    var cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
    el.dispatchEvent(new MouseEvent('contextmenu', {
        bubbles: true, cancelable: true, clientX: cx, clientY: cy,
        button: 2, buttons: 2, view: window
    }));
    return JSON.stringify({ok: true, x: Math.round(cx), y: Math.round(cy)});
})()
"""

_HOVER_TEMPLATES_JS = r"""
(function() {
    var overlay = document.querySelector('.cdk-overlay-container');
    if (!overlay) return JSON.stringify({error: 'no-overlay'});
    var items = Array.from(overlay.querySelectorAll('[class*="menu-item"],[role="menuitem"],li,a'));
    var t = items.find(function(i) { return i.textContent.trim() === 'Templates'; });
    if (!t) return JSON.stringify({error: 'no-templates-item', count: items.length});
    ['mouseenter','mouseover','focus'].forEach(function(e) {
        t.dispatchEvent(new MouseEvent(e, {bubbles: true, cancelable: true, view: window}));
    });
    t.click();
    return JSON.stringify({hovered: true});
})()
"""

_CLICK_SAVE_AS_TEMPLATE_JS = r"""
(function() {
    // Try class selector first (most reliable)
    var btn = document.querySelector('.nav-menu-item_save-as-template');
    if (!btn) {
        // Fallback: text search across all elements
        btn = Array.from(document.querySelectorAll('button,a,[role="menuitem"],li')).find(function(el) {
            return el.textContent.trim().toLowerCase() === 'save as template';
        });
    }
    if (!btn) return JSON.stringify({error: 'not-found'});
    btn.click();
    return JSON.stringify({clicked: true, cls: btn.className.slice(0, 60)});
})()
"""


def step_template() -> None:
    print("\n── STEP 2: Save list template ─────────────────────────────────")
    template_name = "PAI Standard Work List"
    url = _list_url(LIST_IDS["personal_ops"])

    if not navigate_and_verify(url, "Personal Ops", "WORK → Personal Ops list", wait_ms=3500):
        _print_manual("template", template_name)
        return

    # Extra wait for Angular to render the sidebar list items
    time.sleep(3.0)

    # Step 1: right-click Personal Ops via JS contextmenu event (not in a11y tree)
    val = _js_eval(_CONTEXTMENU_JS)
    if '"error"' in val:
        print(f"  ✗ Personal Ops not found in DOM")
        _print_manual("template", template_name)
        return
    time.sleep(1.5)

    # Step 2: hover "Templates" in the context menu to expand the submenu
    hover_val = _js_eval(_HOVER_TEMPLATES_JS)
    if '"error"' in hover_val:
        print(f"  ⚠ Templates hover: {hover_val[:60]} — trying save-as-template directly")
    time.sleep(1.0)

    # Step 3: click "Save as template" in the submenu
    val2 = _js_eval(_CLICK_SAVE_AS_TEMPLATE_JS)
    if '"error"' in val2:
        print(f"  ✗ 'Save as template' not found in context menu: {val2[:60]}")
        _print_manual("template", template_name)
        return
    time.sleep(1.5)

    # Step 4: use a11y tree to type into the name field and save
    tree_data = interceptor("state", wait_after=500)
    tree_text = tree_data.get("elementTree", "")

    # Find the template name input ref
    input_ref = None
    save_ref = None
    for line in tree_text.split("\n"):
        if "Enter template name" in line or ("textbox" in line and "Template name" in line):
            import re
            m = re.search(r'\[e(\d+)\]', line)
            if m:
                input_ref = f"e{m.group(1)}"
        if '"Save Template"' in line or "'Save Template'" in line:
            import re
            m = re.search(r'\[e(\d+)\]', line)
            if m:
                save_ref = f"e{m.group(1)}"

    if input_ref:
        interceptor("click", input_ref, wait_after=200)
        interceptor("keys", "Control+a", wait_after=100)
        interceptor("type", input_ref, template_name, wait_after=300)
    else:
        print("  ⚠ Name input ref not found — template name may be blank")

    if save_ref:
        interceptor("click", save_ref, wait_after=1000)
    else:
        interceptor("keys", "Enter", wait_after=1000)

    # Verify dialog closed
    check = _js_eval(r"""
(function(){
    var inputs=Array.from(document.querySelectorAll('input')).filter(function(i){
        return(i.placeholder||'').indexOf('Enter template name')>=0;
    });
    return JSON.stringify({dialogGone:inputs.length===0});
})()
""")
    if '"dialogGone":true' in check:
        print(f"  ✓ Template '{template_name}' saved")
        screenshot("template-saved")
    else:
        print(f"  ⚠ Dialog may still be open — verify in Chrome")
        screenshot("template-verify")


# ---------------------------------------------------------------------------
# Step 3 — Gantt: hide weekends
# ---------------------------------------------------------------------------

# Checks checkbox/toggle state for weekends setting (read-only, no DOM mutation).
_WEEKENDS_STATE_JS = r"""
(function() {
    var els = Array.from(document.querySelectorAll(
        'input[type="checkbox"],[role="checkbox"],[role="switch"]'
    ));
    var found = els.find(function(el) {
        var label = (el.textContent || el.getAttribute('aria-label') || '');
        var parent = el.closest('[class*="setting"],[class*="toggle"],[class*="gantt"]');
        var ctx = (parent ? parent.textContent : '') + label;
        return ctx.toLowerCase().indexOf('weekend') >= 0;
    });
    if (!found) return JSON.stringify({found: false});
    return JSON.stringify({
        found: true,
        checked: !!(found.checked || found.getAttribute('aria-checked') === 'true')
    });
})()
"""


def step_gantt() -> None:
    print("\n── STEP 3: Gantt — hide weekends ──────────────────────────────")
    url = _folder_url(FOLDER_IDS["active_engagements"])

    if not navigate_and_verify(url, "ACTIVE ENGAGEMENTS", "WORK → ACTIVE ENGAGEMENTS folder", wait_ms=3500):
        _print_manual("gantt")
        return

    screenshot("gantt-folder")

    # Find and click Gantt view tab
    gantt_entries = _extract_refs(interceptor("find", "Gantt", wait_after=500))
    if gantt_entries:
        interceptor("click",_ref(gantt_entries[0]), wait_after=2500)
        screenshot("gantt-view")
    else:
        print("  ⚠ Gantt tab not found — trying direct URL")
        navigate_and_verify(f"{url}?view=gantt", "ACTIVE ENGAGEMENTS", "Gantt URL", wait_ms=3000)

    # Find settings button — collect ref BEFORE opening the settings panel
    settings_entries = _extract_refs(interceptor("find", "Settings", "--role", "button", wait_after=500))
    if not settings_entries:
        settings_entries = _extract_refs(interceptor("find", "Gantt settings", wait_after=500))
    if not settings_entries:
        print("  ✗ Gantt settings button not found")
        _print_manual("gantt")
        return

    # Open settings panel
    interceptor("click",_ref(settings_entries[0]), wait_after=1000)
    screenshot("gantt-settings")

    # Find weekends toggle — collect ref BEFORE reading its state
    wk_entries = _extract_refs(interceptor("find", "Show weekends", wait_after=500))
    if not wk_entries:
        wk_entries = _extract_refs(interceptor("find", "Weekends", wait_after=500))
    if not wk_entries:
        print("  ✗ 'Show weekends' toggle not found")
        _print_manual("gantt")
        return

    wk_ref = _ref(wk_entries[0])

    # Read current state via JS (no DOM mutation, so safe before act)
    val = _js_eval(_WEEKENDS_STATE_JS)
    try:
        state = json.loads(val)
        if state.get("found") and not state.get("checked"):
            print("  ✓ 'Show weekends' already unchecked — nothing to do")
            screenshot("gantt-weekends-done")
            return
    except Exception:
        pass  # couldn't read state — click anyway

    interceptor("click",wk_ref, wait_after=500)
    print("  ✓ 'Show weekends' toggled — verify in Chrome that weekends are now hidden")
    screenshot("gantt-weekends-done")


# ---------------------------------------------------------------------------
# Step 4 — Automations (guided: opens builder, pauses for manual completion)
# ---------------------------------------------------------------------------

AUTOMATIONS = [
    {
        "name":    "FAMILY / KIDS EVENTS — new task → Urgent priority",
        "space":   "family",
        "trigger": "Task created  (in KIDS EVENTS list)",
        "action":  "Set priority → Urgent",
        "url":     f"{BASE_URL}/automations/{SPACE_IDS['family']}",
    },
    {
        "name":    "CAREER / ACTIVE APPLICATIONS — Rejected → move to JD ARCHIVE",
        "space":   "career",
        "trigger": "Status changes to Rejected",
        "action":  "Move task → JD ARCHIVE list",
        "url":     f"{BASE_URL}/automations/{SPACE_IDS['career']}",
    },
    {
        "name":    "PROJECTS / ACTIVE — Shipped → move to ARCHIVE",
        "space":   "projects",
        "trigger": "Status changes to Shipped",
        "action":  "Move task → ARCHIVE list",
        "url":     f"{BASE_URL}/automations/{SPACE_IDS['projects']}",
    },
    {
        "name":    "INBOX / 03 TRIAGE — new task → assign to me",
        "space":   "inbox",
        "trigger": "Task created  (in 03 TRIAGE list)",
        "action":  "Assign task → me",
        "url":     f"{BASE_URL}/automations/{SPACE_IDS['inbox']}",
    },
]


def step_automations() -> None:
    print("\n── STEP 4: Automations ────────────────────────────────────────")
    print("  ClickUp automation builder requires interactive multi-step config.")
    print("  This step opens each space's automation center; you complete each rule.\n")

    for auto in AUTOMATIONS:
        ok = navigate_and_verify(auto["url"], "Automat", auto["name"], wait_ms=3000)
        if not ok:
            print(f"    ✗ Navigation failed — visit manually: {auto['url']}")
            print()
            continue

        # Try to click "New Automation" button
        new_entries = _extract_refs(
            interceptor("find", "New Automation", "--role", "button", wait_after=500)
        )
        if not new_entries:
            new_entries = _extract_refs(
                interceptor("find", "Create Automation", wait_after=300)
            )

        if new_entries:
            interceptor("click",_ref(new_entries[0]), wait_after=1500)
            print(f"    → Automation builder opened ({auto['space'].upper()} space)")
        else:
            print(f"    ⚠ 'New Automation' not found — automation center open in Chrome")

        screenshot(f"automation-{auto['space']}")

        print(f"    Configure:")
        print(f"      Trigger: {auto['trigger']}")
        print(f"      Action:  {auto['action']}")
        print(f"    Press Enter when done (or 's' to skip this one): ", end="", flush=True)
        user_in = input().strip().lower()
        if user_in in ("s", "skip"):
            print(f"    → Skipped")
        else:
            print(f"    ✓ Marked complete")
        print()

    print("  All automation centers visited.")


# ---------------------------------------------------------------------------
# Manual fallback messages
# ---------------------------------------------------------------------------

_MANUAL_STEPS = {
    "template": lambda extra: [
        "WORK space → INTERNAL folder → Personal Ops list",
        "Right-click 'Personal Ops' in the left sidebar",
        "Click 'Save as Template'",
        f"Enter name: '{extra}'",
        "Click Save",
    ],
    "gantt": lambda _: [
        "WORK space → ACTIVE ENGAGEMENTS folder",
        "Click the Gantt view tab in the top bar",
        "Click the gear/settings icon in the Gantt toolbar",
        "Uncheck 'Show weekends'",
    ],
}


def _print_manual(step: str, extra: str = "") -> None:
    fn = _MANUAL_STEPS.get(step)
    if fn:
        print("  Manual steps:")
        for line in fn(extra):
            print(f"    • {line}")


# ---------------------------------------------------------------------------
# Connection check + main
# ---------------------------------------------------------------------------

def _cleanup_clickup_tabs() -> None:
    """Close all existing ClickUp tabs to avoid routing conflicts from duplicate URLs."""
    result = subprocess.run(
        [INTERCEPTOR_BIN, "tabs", "--json"],
        capture_output=True, text=True,
    )
    try:
        raw = json.loads(result.stdout)
        tabs = raw.get("data", []) if isinstance(raw.get("data"), list) else []
    except (json.JSONDecodeError, AttributeError):
        return
    clickup_tabs = [t for t in tabs if "app.clickup.com" in t.get("url", "")]
    if clickup_tabs:
        print(f"  Closing {len(clickup_tabs)} existing ClickUp tab(s)...")
        for tab in clickup_tabs:
            tid = tab.get("id")
            if tid:
                subprocess.run(
                    [INTERCEPTOR_BIN, "tab", "close", str(tid), "--json"],
                    capture_output=True, text=True,
                )
                time.sleep(0.2)


def check_interceptor() -> bool:
    result = subprocess.run(
        [INTERCEPTOR_BIN, "status", "--json"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
        return bool(data.get("daemon"))
    except (json.JSONDecodeError, AttributeError):
        return "daemon: running" in result.stdout


STEPS = {
    "favorites":   step_favorites,
    "template":    step_template,
    "gantt":       step_gantt,
    "automations": step_automations,
}


def main() -> None:
    global DRY_RUN, INTERCEPTOR_BIN

    parser = argparse.ArgumentParser(
        description="Automates ClickUp manual UI setup steps via interceptor."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--step", choices=list(STEPS.keys()))
    args = parser.parse_args()

    DRY_RUN = args.dry_run

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
            print("✗ Could not connect. Make sure:")
            print("  1. Chrome is running")
            print("  2. Interceptor extension is loaded (chrome://extensions)")
            print("  3. interceptor-daemon running (auto-starts on first use)")
            sys.exit(1)
        print("✓ Connected")
        # Close any stale ClickUp tabs first — duplicate URLs confuse interceptor routing.
        _cleanup_clickup_tabs()
        # Open one stable ClickUp tab. Omit --no-wait so the content script is
        # fully initialized before we start navigating — eval reliability depends on this.
        print("  Opening fresh ClickUp tab...")
        interceptor("open", BASE_URL, "--activate", wait_after=1000)
        print()

    steps_to_run = [args.step] if args.step else list(STEPS.keys())
    print(f"Running: {', '.join(steps_to_run)}\n")

    for step_name in steps_to_run:
        try:
            STEPS[step_name]()
        except Exception as e:
            print(f"\n✗ Step '{step_name}' raised: {e}")

    print("\n────────────────────────────────────────────────────────────────")
    print("setup_ui.py complete.")


if __name__ == "__main__":
    main()
