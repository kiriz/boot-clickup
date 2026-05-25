#!/usr/bin/env python3
"""
setup_playwright.py — Playwright-based ClickUp manual UI automation.

Replaces setup_ui.py (Interceptor-based). Uses a persistent Chrome profile so
the script reuses your existing ClickUp login + cookies + Cloudflare clearance.

Why Playwright (vs Interceptor):
  • locator('text=...') matches raw DOM — ClickUp sidebar items live in DOM but
    NOT in the accessibility tree, so interceptor find returns empty for them.
  • click(button='right') issues a real CDP mouse event sequence that Angular CDK
    overlays respond to, replacing fragile dispatchEvent('contextmenu') hacks.
  • Auto-waiting (wait_for / locators) replaces every manual time.sleep().
  • Single persistent context = stays logged in, no Cloudflare re-challenge.

Steps:
  1. favorites    — add 6 items to the Favorites bar in morning-review order
  2. template     — save WORK / Personal Ops as "PAI Standard Work List"
  3. gantt        — hide weekends in WORK / ACTIVE ENGAGEMENTS Gantt view
  4. automations  — guided: opens automation builder for each rule

Setup once:
  pip install playwright pyyaml && playwright install chromium

Usage:
  python setup_playwright.py                          # all steps
  python setup_playwright.py --dry-run                # print only
  python setup_playwright.py --step favorites         # one step
  python setup_playwright.py --config path/to.yaml    # custom config
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import yaml

try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Error as PlaywrightError,
        Page,
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )
except ImportError:  # pragma: no cover - import-time guard
    print(
        "✗ playwright is not installed.\n"
        "  Run: pip install playwright pyyaml && playwright install chromium",
        file=sys.stderr,
    )
    raise


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "PAI" / "USER" / "CLICKUP.yaml"
DEFAULT_CHROME_PROFILE = (
    Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default"
)
SCREENSHOTS_DIR = Path("screenshots")
DEFAULT_TIMEOUT_MS = 20_000
TEMPLATE_NAME = "PAI Standard Work List"


# ---------------------------------------------------------------------------
# Config — single source of truth, never hardcode IDs
# ---------------------------------------------------------------------------


class ConfigError(RuntimeError):
    """Raised when the YAML config is missing required keys."""


@dataclass
class ClickUpConfig:
    """Loads ClickUp IDs from YAML and exposes URL helpers + lookups."""

    path: Path
    workspace_id: str = ""
    plan: str = ""
    spaces: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "ClickUpConfig":
        if not path.exists():
            raise ConfigError(f"Config not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        ws = raw.get("workspace_id")
        if not ws:
            raise ConfigError(f"'workspace_id' missing in {path}")
        return cls(
            path=path,
            workspace_id=str(ws),
            plan=str(raw.get("plan", "")),
            spaces=raw.get("spaces") or {},
            raw=raw,
        )

    # ---------- URL builders ----------

    @property
    def base_url(self) -> str:
        return f"https://app.clickup.com/{self.workspace_id}"

    def list_url(self, list_id: str) -> str:
        return f"{self.base_url}/v/l/li/{list_id}"

    def folder_url(self, folder_id: str) -> str:
        return f"{self.base_url}/v/f/{folder_id}"

    def space_url(self, space_id: str) -> str:
        return f"{self.base_url}/v/s/{space_id}"

    def automation_urls(self, space_id: str) -> list[str]:
        """Candidate URLs for a space's automation center (try in order)."""
        return [
            f"{self.base_url}/automations/{space_id}",
            f"{self.base_url}/v/s/{space_id}?settings=automations",
        ]

    # ---------- Lookups ----------

    def _space(self, space_name: str) -> dict[str, Any]:
        node = self.spaces.get(space_name)
        if not node:
            raise ConfigError(f"Space '{space_name}' not in config")
        return node

    def get_space_id(self, space_name: str) -> str:
        sid = self._space(space_name).get("id")
        if not sid:
            raise ConfigError(f"Space '{space_name}' has no id")
        return str(sid)

    def get_list_id(self, space_name: str, list_name: str) -> str:
        lists = self._space(space_name).get("lists") or {}
        lid = lists.get(list_name)
        if not lid:
            raise ConfigError(f"List '{list_name}' not under space '{space_name}'")
        return str(lid)

    def _folder(self, space_name: str, folder_name: str) -> dict[str, Any]:
        folders = self._space(space_name).get("folders") or {}
        node = folders.get(folder_name)
        if not node:
            raise ConfigError(
                f"Folder '{folder_name}' not under space '{space_name}'"
            )
        return node

    def get_folder_id(self, space_name: str, folder_name: str) -> str:
        fid = self._folder(space_name, folder_name).get("id")
        if not fid:
            raise ConfigError(
                f"Folder '{folder_name}' under '{space_name}' has no id"
            )
        return str(fid)

    def get_folder_list_id(
        self, space_name: str, folder_name: str, list_name: str
    ) -> str:
        folder = self._folder(space_name, folder_name)
        lists = folder.get("lists") or {}
        lid = lists.get(list_name)
        if not lid:
            raise ConfigError(
                f"List '{list_name}' not under {space_name}/{folder_name}"
            )
        return str(lid)


# ---------------------------------------------------------------------------
# Shared runtime state — dry-run flag and screenshot helper
# ---------------------------------------------------------------------------


@dataclass
class RunContext:
    config: ClickUpConfig
    dry_run: bool = False

    def __post_init__(self) -> None:
        if not self.dry_run:
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Logging shorthand ----

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    def dry(self, msg: str) -> None:
        if self.dry_run:
            print(f"    [dry-run] {msg}", flush=True)

    # ---- Screenshots ----

    def screenshot(self, page: Page, step: str, label: str) -> Optional[Path]:
        if self.dry_run:
            self.dry(f"screenshot {step}-{label}")
            return None
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", label).strip("-").lower() or "frame"
        out = SCREENSHOTS_DIR / f"{step}-{safe}.png"
        try:
            page.screenshot(path=str(out), full_page=False)
            print(f"    📸 {out}", flush=True)
        except PlaywrightError as exc:
            print(f"    ⚠ screenshot failed: {exc}", flush=True)
            return None
        return out


# ---------------------------------------------------------------------------
# Page utilities
# ---------------------------------------------------------------------------


def goto(page: Page, url: str, *, label: str = "") -> bool:
    """Navigate and wait for ClickUp's main shell to settle."""
    try:
        page.goto(url, wait_until="domcontentloaded")
        # ClickUp is an SPA; networkidle is the cleanest "Angular ready" signal.
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeoutError:
            # Some views keep websockets open; press on if DOM is interactive.
            pass
    except PlaywrightError as exc:
        print(f"    ✗ goto failed ({label or url}): {exc}", flush=True)
        return False
    return True


def first_visible(page: Page, selectors: Iterable[str], timeout: int = 5_000):
    """Return the first selector that becomes visible, else None."""
    deadline = time.monotonic() + (timeout / 1000)
    for sel in selectors:
        remaining = max(0, deadline - time.monotonic())
        if remaining <= 0:
            return None
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=int(remaining * 1000))
            return loc
        except PlaywrightTimeoutError:
            continue
    return None


# ---------------------------------------------------------------------------
# Step 1 — Favorites
# ---------------------------------------------------------------------------


def _favorite_items(config: ClickUpConfig) -> list[tuple[str, str, str]]:
    """Build (label, kind, url) tuples — all IDs derived from config."""
    items: list[tuple[str, str, Callable[[ClickUpConfig], str]]] = [
        ("FAMILY → KIDS EVENTS", "list",
            lambda c: c.get_list_id("family", "kids_events")),
        ("HOME → SEASONAL CALENDAR", "list",
            lambda c: c.get_list_id("home", "seasonal_calendar")),
        ("INBOX → 01 TODAY", "list",
            lambda c: c.get_list_id("inbox", "today")),
        ("WORK → ACTIVE ENGAGEMENTS", "folder",
            lambda c: c.get_folder_id("work", "active_engagements")),
        ("PROJECTS → ACTIVE", "list",
            lambda c: c.get_list_id("projects", "active")),
        ("CAREER → ACTIVE APPLICATIONS", "list",
            lambda c: c.get_folder_list_id("career", "job_pipeline",
                                           "active_applications")),
    ]
    resolved: list[tuple[str, str, str]] = []
    for label, kind, resolver in items:
        entity_id = resolver(config)
        url = (config.list_url(entity_id) if kind == "list"
               else config.folder_url(entity_id))
        resolved.append((label, kind, url))
    return resolved


_FAVORITE_BTN_SELECTOR = (
    'button[aria-label*="avorite"]:not(.expand-button),'
    ' [role="button"][aria-label*="avorite"]:not(.expand-button)'
)


def _favorite_one(page: Page, ctx: RunContext, label: str, url: str) -> str:
    """Returns 'added' | 'already' | 'failed'."""
    if not goto(page, url, label=label):
        return "failed"

    try:
        btn = page.locator(_FAVORITE_BTN_SELECTOR).first
        btn.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError:
        print("    ✗ favorite button not visible", flush=True)
        return "failed"

    aria = (btn.get_attribute("aria-label") or "").lower()
    if "remove" in aria:
        print("    ✓ already in Favorites (button says 'remove')", flush=True)
        return "already"

    try:
        btn.click()
    except PlaywrightError as exc:
        print(f"    ✗ click failed: {exc}", flush=True)
        return "failed"

    overlay = page.locator(".cdk-overlay-container")
    try:
        fav_item = overlay.get_by_text("Favorites", exact=True).first
        fav_item.wait_for(state="visible", timeout=8_000)
    except PlaywrightTimeoutError:
        print("    ⚠ 'Favorites' option not in overlay", flush=True)
        return "failed"

    try:
        # If already selected the overlay marks the item — click still toggles
        # off, so check first via class/aria.
        item_class = (fav_item.get_attribute("class") or "").lower()
        aria_checked = (fav_item.get_attribute("aria-checked") or "").lower()
        if "menu-item-selected" in item_class or aria_checked == "true":
            print("    ✓ already in Favorites (item pre-selected)", flush=True)
            page.keyboard.press("Escape")
            return "already"
        fav_item.click()
    except PlaywrightError as exc:
        print(f"    ✗ overlay click failed: {exc}", flush=True)
        return "failed"

    return "added"


def step_favorites(page: Page, ctx: RunContext) -> None:
    ctx.log("\n── STEP 1: Favorites bar ─────────────────────────────────────")
    items = _favorite_items(ctx.config)

    if ctx.dry_run:
        for label, kind, url in items:
            ctx.dry(f"favorite {label} ({kind}) → {url}")
        return

    added = already = failed = 0
    for label, _kind, url in items:
        print(f"  ▸ {label}", flush=True)
        status = _favorite_one(page, ctx, label, url)
        if status == "added":
            added += 1
            ctx.screenshot(page, "fav", label)
        elif status == "already":
            already += 1
        else:
            failed += 1
            print("    ↳ manual: hover the item in the sidebar → click ★",
                  flush=True)

    total = len(items)
    ctx.log(
        f"\n  Result: {added + already}/{total} in Favorites "
        f"({added} added, {already} already set, {failed} failed)"
    )


# ---------------------------------------------------------------------------
# Step 2 — Save list template
# ---------------------------------------------------------------------------


def _find_sidebar_item(page: Page, name: str):
    """Locate the sidebar entry for a given list/folder. Falls back to
    text-only match if a <nav> wrapper isn't present."""
    candidates = [
        page.locator('nav').get_by_text(name, exact=True),
        page.locator('[class*="sidebar"]').get_by_text(name, exact=True),
        page.locator('aside').get_by_text(name, exact=True),
        page.get_by_text(name, exact=True),
    ]
    for loc in candidates:
        try:
            loc.first.wait_for(state="visible", timeout=4_000)
            return loc.first
        except PlaywrightTimeoutError:
            continue
    return None


def step_template(page: Page, ctx: RunContext) -> None:
    ctx.log("\n── STEP 2: Save list template ────────────────────────────────")
    list_id = ctx.config.get_folder_list_id("work", "internal", "personal_ops")
    url = ctx.config.list_url(list_id)

    if ctx.dry_run:
        ctx.dry(f"open {url}")
        ctx.dry(f"right-click 'Personal Ops' → Templates → Save as Template")
        ctx.dry(f"fill template name '{TEMPLATE_NAME}'")
        return

    if not goto(page, url, label="WORK → Personal Ops"):
        _print_manual_template()
        return

    try:
        page.wait_for_selector("text=Personal Ops", timeout=15_000)
    except PlaywrightTimeoutError:
        print("  ✗ 'Personal Ops' never appeared", flush=True)
        _print_manual_template()
        return

    sidebar_item = _find_sidebar_item(page, "Personal Ops")
    if sidebar_item is None:
        print("  ✗ Personal Ops sidebar entry not found", flush=True)
        _print_manual_template()
        return

    try:
        sidebar_item.click(button="right")
    except PlaywrightError as exc:
        print(f"  ✗ right-click failed: {exc}", flush=True)
        _print_manual_template()
        return

    overlay = page.locator(".cdk-overlay-container")
    try:
        overlay.locator('[class*="menu"]').first.wait_for(
            state="visible", timeout=8_000
        )
    except PlaywrightTimeoutError:
        print("  ✗ context menu didn't open", flush=True)
        _print_manual_template()
        return

    # Hover Templates → CDK submenu animates in
    try:
        overlay.get_by_text("Templates", exact=False).first.hover()
        page.wait_for_timeout(500)
    except PlaywrightError as exc:
        print(f"  ⚠ Templates hover issue: {exc}", flush=True)

    try:
        overlay.get_by_text(re.compile(r"^save as template$", re.I)).first.click()
    except PlaywrightError as exc:
        print(f"  ✗ 'Save as Template' click failed: {exc}", flush=True)
        _print_manual_template()
        return

    # Dialog appears — type the template name
    name_input = first_visible(
        page,
        [
            'input[placeholder*="template" i]',
            'input[placeholder*="name" i]',
            '.cdk-overlay-container input[type="text"]',
        ],
        timeout=8_000,
    )
    if name_input is None:
        print("  ⚠ name field not found — template may save unnamed", flush=True)
    else:
        try:
            name_input.fill(TEMPLATE_NAME)
        except PlaywrightError as exc:
            print(f"  ⚠ fill failed: {exc}", flush=True)

    try:
        page.keyboard.press("Enter")
    except PlaywrightError:
        pass

    # Confirm dialog cleared
    try:
        page.wait_for_selector(
            'input[placeholder*="template" i]',
            state="hidden",
            timeout=8_000,
        )
        print(f"  ✓ Template '{TEMPLATE_NAME}' saved", flush=True)
        ctx.screenshot(page, "template", "saved")
    except PlaywrightTimeoutError:
        print("  ⚠ dialog still visible — confirm manually", flush=True)
        ctx.screenshot(page, "template", "verify")


def _print_manual_template() -> None:
    print("  Manual fallback:", flush=True)
    for line in [
        "WORK → INTERNAL → Personal Ops list",
        "Right-click 'Personal Ops' in the sidebar",
        "Templates → Save as Template",
        f"Enter name: '{TEMPLATE_NAME}'",
        "Click Save",
    ]:
        print(f"    • {line}", flush=True)


# ---------------------------------------------------------------------------
# Step 3 — Gantt: hide weekends
# ---------------------------------------------------------------------------


def _ensure_gantt_view(page: Page) -> bool:
    """Click the existing Gantt tab or add one if missing."""
    gantt_tab = page.get_by_role("tab", name=re.compile("gantt", re.I))
    try:
        gantt_tab.first.wait_for(state="visible", timeout=4_000)
        gantt_tab.first.click()
        return True
    except PlaywrightTimeoutError:
        pass

    # Try add-view affordances
    add_btn = first_visible(
        page,
        [
            'button[aria-label*="add view" i]',
            'button[aria-label*="add a view" i]',
            'button[aria-label="+"]',
        ],
        timeout=3_000,
    )
    if add_btn is not None:
        try:
            add_btn.click()
            page.locator(".cdk-overlay-container").get_by_text(
                "Gantt", exact=False
            ).first.click()
            return True
        except PlaywrightError as exc:
            print(f"    ⚠ add-view path failed: {exc}", flush=True)

    # Last resort: append ?view=gantt to URL
    try:
        current = page.url
        joiner = "&" if "?" in current else "?"
        page.goto(f"{current}{joiner}view=gantt", wait_until="domcontentloaded")
        return True
    except PlaywrightError as exc:
        print(f"    ✗ direct Gantt URL failed: {exc}", flush=True)
        return False


def step_gantt(page: Page, ctx: RunContext) -> None:
    ctx.log("\n── STEP 3: Gantt — hide weekends ─────────────────────────────")
    folder_id = ctx.config.get_folder_id("work", "active_engagements")
    url = ctx.config.folder_url(folder_id)

    if ctx.dry_run:
        ctx.dry(f"open {url}")
        ctx.dry("switch to Gantt view → settings → uncheck Show weekends")
        return

    if not goto(page, url, label="WORK → ACTIVE ENGAGEMENTS"):
        _print_manual_gantt()
        return

    ctx.screenshot(page, "gantt", "folder")

    if not _ensure_gantt_view(page):
        _print_manual_gantt()
        return

    # Wait for Gantt-specific UI to render
    try:
        page.wait_for_selector(
            '[class*="gantt"], [class*="Gantt"]', timeout=10_000
        )
    except PlaywrightTimeoutError:
        print("  ⚠ Gantt view didn't render", flush=True)

    ctx.screenshot(page, "gantt", "view")

    # Gantt-specific settings button — scope to the Gantt toolbar to avoid the
    # global ClickUp settings cog
    settings_btn = first_visible(
        page,
        [
            '[class*="gantt"] button[aria-label*="setting" i]',
            '[class*="gantt-toolbar"] [aria-label*="setting" i]',
            '[class*="gantt"] [aria-label*="setting" i]',
            'button[aria-label*="gantt setting" i]',
        ],
        timeout=8_000,
    )
    if settings_btn is None:
        print("  ✗ Gantt settings button not found", flush=True)
        _print_manual_gantt()
        return

    try:
        settings_btn.click()
    except PlaywrightError as exc:
        print(f"  ✗ settings click failed: {exc}", flush=True)
        _print_manual_gantt()
        return

    ctx.screenshot(page, "gantt", "settings")

    # Find the "Show weekends" row and its toggle
    try:
        row = page.get_by_text(re.compile("show weekends", re.I)).first
        row.wait_for(state="visible", timeout=8_000)
    except PlaywrightTimeoutError:
        print("  ✗ 'Show weekends' label not found", flush=True)
        _print_manual_gantt()
        return

    toggle = row.locator(
        'xpath=ancestor::*[self::div or self::li][1]'
        '//input[@type="checkbox"] | ancestor::*[self::div or self::li][1]'
        '//*[@role="switch"] | ancestor::*[self::div or self::li][1]'
        '//*[@role="checkbox"]'
    ).first

    found_toggle = False
    try:
        toggle.wait_for(state="attached", timeout=3_000)
        found_toggle = True
    except PlaywrightTimeoutError:
        pass

    if found_toggle:
        try:
            is_on = toggle.is_checked()
        except PlaywrightError:
            is_on = True  # default: assume on, click to flip
        if is_on:
            try:
                toggle.click()
                print("  ✓ 'Show weekends' toggled off", flush=True)
            except PlaywrightError as exc:
                print(f"  ⚠ toggle click failed: {exc}", flush=True)
        else:
            print("  ✓ 'Show weekends' already off", flush=True)
    else:
        # Some toggle rows accept a click on the label itself
        try:
            row.click()
            print("  ✓ 'Show weekends' row clicked (label-as-toggle)",
                  flush=True)
        except PlaywrightError as exc:
            print(f"  ✗ label click failed: {exc}", flush=True)
            _print_manual_gantt()
            return

    ctx.screenshot(page, "gantt", "weekends-done")


def _print_manual_gantt() -> None:
    print("  Manual fallback:", flush=True)
    for line in [
        "WORK → ACTIVE ENGAGEMENTS folder",
        "Click the Gantt view tab",
        "Click the gear/settings icon in the Gantt toolbar",
        "Uncheck 'Show weekends'",
    ]:
        print(f"    • {line}", flush=True)


# ---------------------------------------------------------------------------
# Step 4 — Automations (interactive / guided)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AutomationRule:
    label: str
    space: str
    trigger: str
    action: str


AUTOMATION_RULES: list[AutomationRule] = [
    AutomationRule(
        label="FAMILY / KIDS EVENTS — task created → Urgent",
        space="family",
        trigger="Task created  (scope to kids_events list)",
        action="Set priority → Urgent",
    ),
    AutomationRule(
        label="CAREER / ACTIVE APPLICATIONS — Rejected → JD ARCHIVE",
        space="career",
        trigger="Status changes to Rejected",
        action="Move task → jd_archive list",
    ),
    AutomationRule(
        label="PROJECTS / ACTIVE — Shipped → ARCHIVE",
        space="projects",
        trigger="Status changes to Shipped",
        action="Move task → archive list",
    ),
    AutomationRule(
        label="INBOX / 03 TRIAGE — task created → assign to me",
        space="inbox",
        trigger="Task created  (scope to triage list)",
        action="Assign task → me",
    ),
]


def _open_automation_center(page: Page, urls: list[str]) -> bool:
    """Try each candidate URL; success = the page mentions 'Automation'."""
    for url in urls:
        if not goto(page, url, label=f"automation center {url}"):
            continue
        try:
            page.wait_for_selector("text=/automation/i", timeout=8_000)
            return True
        except PlaywrightTimeoutError:
            continue
    return False


def step_automations(page: Page, ctx: RunContext) -> None:
    ctx.log("\n── STEP 4: Automations ───────────────────────────────────────")
    ctx.log("  ClickUp automations need interactive multi-step config.")
    ctx.log("  Each rule opens its space's automation center; you complete it.\n")

    if ctx.dry_run:
        for rule in AUTOMATION_RULES:
            sid = ctx.config.get_space_id(rule.space)
            ctx.dry(f"open automation center for space '{rule.space}' "
                    f"(id={sid})")
            ctx.dry(f"  trigger: {rule.trigger}")
            ctx.dry(f"  action:  {rule.action}")
        return

    for rule in AUTOMATION_RULES:
        try:
            space_id = ctx.config.get_space_id(rule.space)
        except ConfigError as exc:
            print(f"  ✗ {exc}", flush=True)
            continue

        urls = ctx.config.automation_urls(space_id)
        print(f"  ▸ {rule.label}", flush=True)

        opened = _open_automation_center(page, urls)
        if not opened:
            print("    ✗ couldn't open automation center — visit manually:",
                  flush=True)
            for u in urls:
                print(f"      {u}", flush=True)
        else:
            # Try the "New Automation" button (don't fail if it's not there)
            new_btn = first_visible(
                page,
                [
                    'button:has-text("New Automation")',
                    'button:has-text("Create Automation")',
                    '[role="button"]:has-text("New Automation")',
                ],
                timeout=3_000,
            )
            if new_btn is not None:
                try:
                    new_btn.click()
                    page.wait_for_timeout(1_000)
                    print("    → automation builder opened", flush=True)
                except PlaywrightError as exc:
                    print(f"    ⚠ couldn't click 'New Automation': {exc}",
                          flush=True)
            else:
                print("    ⚠ 'New Automation' not found — center is open",
                      flush=True)

        ctx.screenshot(page, "automation", rule.space)

        print("    Configure:", flush=True)
        print(f"      Trigger: {rule.trigger}", flush=True)
        print(f"      Action:  {rule.action}", flush=True)
        try:
            answer = input(
                "    Press Enter when done (or 's' to skip): "
            ).strip().lower()
        except EOFError:
            answer = ""
        if answer in ("s", "skip"):
            print("    → skipped", flush=True)
        else:
            print("    ✓ marked complete", flush=True)
        print(flush=True)

    print("  All automation centers visited.", flush=True)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


STEPS: dict[str, Callable[[Page, RunContext], None]] = {
    "favorites":   step_favorites,
    "template":    step_template,
    "gantt":       step_gantt,
    "automations": step_automations,
}


def _launch_context(
    profile_path: Path,
    headless: bool = False,
    slow_mo_ms: int = 100,
) -> tuple[Any, BrowserContext, Page]:
    """Return (playwright, context, page). Caller must stop playwright."""
    pw = sync_playwright().start()
    try:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=headless,
            channel="chrome",
            slow_mo=slow_mo_ms,
            viewport=None,  # let the real window size apply
        )
    except PlaywrightError as exc:
        pw.stop()
        raise RuntimeError(
            f"Failed to launch persistent Chrome context at {profile_path}.\n"
            "  Common causes:\n"
            "    • Chrome is already running with this profile (close it first)\n"
            "    • Chrome channel isn't installed — install Google Chrome or\n"
            "      drop channel='chrome' to use bundled Chromium\n"
            f"  Underlying error: {exc}"
        ) from exc

    context.set_default_timeout(DEFAULT_TIMEOUT_MS)
    page = context.pages[0] if context.pages else context.new_page()
    return pw, context, page


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Playwright-based ClickUp manual UI automation. "
            "Replaces setup_ui.py."
        )
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print planned actions without driving the browser.",
    )
    parser.add_argument(
        "--step", choices=list(STEPS.keys()),
        help="Run only one step (default: all).",
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH,
        help=f"Path to ClickUp YAML (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--profile", type=Path, default=DEFAULT_CHROME_PROFILE,
        help=(
            "Chrome user-data-dir to reuse (default: "
            f"{DEFAULT_CHROME_PROFILE})"
        ),
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run Chrome headless (rarely useful — ClickUp dislikes headless).",
    )
    parser.add_argument(
        "--slow-mo", type=int, default=100,
        help="Slow-mo ms between actions (gives Angular CDK time to render).",
    )
    args = parser.parse_args()

    # Load config (always — even dry-run needs it for URL preview)
    try:
        config = ClickUpConfig.load(args.config)
    except ConfigError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        sys.exit(1)

    ctx = RunContext(config=config, dry_run=args.dry_run)
    steps_to_run = [args.step] if args.step else list(STEPS.keys())

    print(f"Config:  {args.config}")
    print(f"Steps:   {', '.join(steps_to_run)}")
    if args.dry_run:
        print("DRY RUN — no browser actions taken\n")
        for name in steps_to_run:
            # Each step accepts a Page; pass None in dry-run since we don't
            # exercise Page methods (steps guard on ctx.dry_run first).
            STEPS[name](None, ctx)  # type: ignore[arg-type]
        print("\nsetup_playwright.py (dry-run) complete.")
        return

    print(f"Profile: {args.profile}")
    print()

    pw, browser_ctx, page = _launch_context(
        profile_path=args.profile,
        headless=args.headless,
        slow_mo_ms=args.slow_mo,
    )

    try:
        # Park on the workspace root once so subsequent navigations don't fight
        # a blank tab.
        goto(page, config.base_url, label="ClickUp root")
        for name in steps_to_run:
            try:
                STEPS[name](page, ctx)
            except Exception as exc:  # noqa: BLE001 — surface every failure
                print(f"\n✗ Step '{name}' raised: {exc}", flush=True)
        print("\n──────────────────────────────────────────────────────────────")
        print("setup_playwright.py complete.")
    finally:
        try:
            browser_ctx.close()
        except PlaywrightError:
            pass
        pw.stop()


if __name__ == "__main__":
    main()
