#!/usr/bin/env python3
"""
boot-clickup — Personal Life OS Setup Script
=============================================
Builds a complete personal life management system in ClickUp
from a single user-editable config file (config.yaml).

Usage:
  export CLICKUP_API_KEY=pk_xxxxx
  python setup.py

  python setup.py --api-key pk_xxxxx --config config.yaml
  python setup.py --dry-run        # preview all API calls, no changes made
  python setup.py --output my_ids.yaml

Requirements: Python 3.8+, PyYAML (pip install pyyaml)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Optional


# ---------------------------------------------------------------------------
# YAML loader — tries PyYAML, falls back to a minimal built-in parser
# ---------------------------------------------------------------------------

def load_yaml(path: str) -> dict:
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:
        print("PyYAML not found. Install it: pip install pyyaml")
        print("Attempting minimal built-in YAML parse (basic key: value only)...")
        return _minimal_yaml_load(path)


def _minimal_yaml_load(path: str) -> dict:
    """
    Extremely minimal YAML parser for simple key: value and nested dicts.
    Only here as a last resort — install PyYAML for full config support.
    """
    raise RuntimeError(
        "boot-clickup requires PyYAML for config parsing.\n"
        "Install it with: pip install pyyaml\n"
        "Or with uv: uv pip install pyyaml"
    )


# ---------------------------------------------------------------------------
# ClickUp API client
# ---------------------------------------------------------------------------

class ClickUpAPI:
    BASE = "https://api.clickup.com/api/v2"
    RATE_DELAY = 0.25  # seconds between requests

    def __init__(self, api_key: str, dry_run: bool = False):
        self.api_key = api_key
        self.dry_run = dry_run
        self._call_count = 0

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        self._call_count += 1
        url = f"{self.BASE}{path}"

        if self.dry_run:
            label = f"[DRY RUN #{self._call_count}] {method} {path}"
            if body:
                label += f"\n    body: {json.dumps(body, ensure_ascii=False)[:120]}"
            print(f"    {label}")
            # Return a synthetic ID so downstream code doesn't crash
            synthetic = f"DRY_{path.replace('/', '_').strip('_')}"
            name = (body or {}).get("name", "")
            return {"id": synthetic, "name": name, "view": {"id": synthetic + "_view", "name": name}}

        args = ["curl", "-s", "-X", method, url,
                "-H", f"Authorization: {self.api_key}",
                "-H", "Content-Type: application/json"]
        if body:
            args += ["-d", json.dumps(body, ensure_ascii=False)]

        result = subprocess.run(args, capture_output=True, text=True)
        time.sleep(self.RATE_DELAY)

        if not result.stdout.strip():
            return {}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"    WARNING: non-JSON response for {method} {path}: {result.stdout[:80]}")
            return {}

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body)

    def put(self, path: str, body: dict) -> dict:
        return self._request("PUT", path, body)

    # --- Higher-level helpers ---

    def get_workspace_id(self) -> str:
        if self.dry_run:
            return "DRY_WORKSPACE_ID"
        data = self.get("/team")
        teams = data.get("teams", [])
        if not teams:
            raise ValueError(
                "No workspaces found for this API key.\n"
                "  • Check the key at: ClickUp → Settings → Apps → API Token\n"
                "  • Make sure you're using a Personal API Token, not an OAuth token"
            )
        return teams[0]["id"]

    def create_space(self, workspace_id: str, name: str, color: str) -> str:
        data = self.post(f"/team/{workspace_id}/space", {
            "name": name,
            "color": color,
            "features": {
                "due_dates": {"enabled": True, "start_date": True},
                "custom_fields": {"enabled": True},
                "time_tracking": {"enabled": False},
                "sprints": {"enabled": False},
            }
        })
        return data.get("id", "")

    def enable_custom_fields(self, space_id: str) -> None:
        self.put(f"/space/{space_id}", {"features": {"custom_fields": {"enabled": True}}})

    def create_folder(self, space_id: str, name: str) -> str:
        return self.post(f"/space/{space_id}/folder", {"name": name}).get("id", "")

    def create_list_in_space(self, space_id: str, name: str) -> str:
        return self.post(f"/space/{space_id}/list", {"name": name}).get("id", "")

    def create_list_in_folder(self, folder_id: str, name: str) -> str:
        return self.post(f"/folder/{folder_id}/list", {"name": name}).get("id", "")

    def add_custom_field(self, list_id: str, field: dict) -> Optional[str]:
        payload = {"name": field["name"], "type": field["type"]}
        if "options" in field:
            payload["type_config"] = {
                "options": [{"name": o, "orderindex": i} for i, o in enumerate(field["options"])]
            }
        elif "type_config" in field:
            payload["type_config"] = field["type_config"]
        data = self.post(f"/list/{list_id}/field", payload)
        return None if "err" in data else data.get("id")

    def add_view(self, entity_type: str, entity_id: str, view_type: str) -> Optional[str]:
        data = self.post(f"/{entity_type}/{entity_id}/view",
                         {"name": view_type.capitalize(), "type": view_type})
        v = data.get("view", data)
        return v.get("id")

    def create_task(self, list_id: str, name: str, description: str = "",
                    parent: Optional[str] = None) -> str:
        body: dict = {"name": name}
        if description:
            body["description"] = description
        if parent:
            body["parent"] = parent
        return self.post(f"/list/{list_id}/task", body).get("id", "")


# ---------------------------------------------------------------------------
# Build engine — reads config dict, calls API, returns ID map
# ---------------------------------------------------------------------------

def build(api: ClickUpAPI, cfg: dict) -> dict:
    print("\n=== boot-clickup: Personal Life OS Setup ===\n")

    # 1. Workspace
    print("Step 1/6  Resolving workspace...")
    workspace_id = api.get_workspace_id()
    print(f"          Workspace ID: {workspace_id}\n")

    id_map: dict = {
        "workspace_id": workspace_id,
        "spaces": {},
    }

    space_ids: dict[str, str] = {}
    list_ids: dict[str, dict[str, str]] = {}
    folder_ids: dict[str, dict[str, str]] = {}

    # 2. Spaces
    print("Step 2/6  Creating spaces...")
    for space_key, space_cfg in cfg["spaces"].items():
        sid = api.create_space(workspace_id, space_cfg["name"], space_cfg.get("color", "#87909E"))
        api.enable_custom_fields(sid)
        space_ids[space_key] = sid
        list_ids[space_key] = {}
        folder_ids[space_key] = {}
        print(f"          ✓ {space_cfg['name']}  ({sid})")

    print()

    # 3. Folders + Lists
    print("Step 3/6  Creating folders and lists...")
    for space_key, space_cfg in cfg["spaces"].items():
        sid = space_ids[space_key]

        # Direct lists (no folder)
        for list_key, list_cfg in space_cfg.get("lists", {}).items():
            lid = api.create_list_in_space(sid, list_cfg["name"])
            list_ids[space_key][list_key] = lid
            # Add any views defined on the list
            for vtype in list_cfg.get("views", []):
                api.add_view("list", lid, vtype)
            print(f"          ✓ {space_cfg['name']} / {list_cfg['name']}  ({lid})")

        # Folders → lists inside each folder
        for folder_key, folder_cfg in space_cfg.get("folders", {}).items():
            fid = api.create_folder(sid, folder_cfg["name"])
            folder_ids[space_key][folder_key] = fid
            print(f"          ✓ {space_cfg['name']} / 📁 {folder_cfg['name']}  ({fid})")

            # Views on the folder
            for vtype in folder_cfg.get("views", []):
                api.add_view("folder", fid, vtype)

            for list_key, list_cfg in folder_cfg.get("lists", {}).items():
                lid = api.create_list_in_folder(fid, list_cfg["name"])
                list_ids[space_key][list_key] = lid
                print(f"               ✓ {list_cfg['name']}  ({lid})")

    print()

    # 4. Work-tracking columns (Start Date + % Completed)
    print("Step 4/6  Adding columns to work-tracking lists...")
    work_fields = [{"name": "Start Date", "type": "date"},
                   {"name": "% Completed", "type": "number"}]

    for space_key, list_keys in cfg.get("work_tracking_lists", {}).items():
        for lk in list_keys:
            lid = list_ids.get(space_key, {}).get(lk)
            if not lid:
                print(f"          WARNING: list '{space_key}/{lk}' not found — skipping")
                continue
            for fld in work_fields:
                api.add_custom_field(lid, fld)
            print(f"          ✓ {space_key} / {lk}")

    print()

    # 5. Job pipeline custom fields
    print("Step 5/6  Adding job pipeline custom fields...")
    apps_lid = list_ids.get("career", {}).get("active_applications")
    if apps_lid:
        for fld in cfg.get("job_pipeline_fields", []):
            api.add_custom_field(apps_lid, fld)
            print(f"          ✓ ACTIVE APPLICATIONS / {fld['name']}")
    else:
        print("          (no career/active_applications list found — skipping)")

    print()

    # 6. Home seasonal tasks
    print("Step 6/6  Pre-populating HOME / SEASONAL CALENDAR...")
    seasonal_lid = list_ids.get("home", {}).get("seasonal_calendar")
    if seasonal_lid:
        for task in cfg.get("seasonal_tasks", []):
            desc = f"Recurrence: {task.get('recurrence', 'annual')}"
            if task.get("note"):
                desc += f"\nNote: {task['note']}"
            api.create_task(seasonal_lid, task["name"], description=desc)
            print(f"          ✓ {task['name']}")
    else:
        print("          (no home/seasonal_calendar list found — skipping)")

    print()

    # Build output ID structure
    for space_key, space_cfg in cfg["spaces"].items():
        entry: dict = {
            "id": space_ids[space_key],
            "name": space_cfg["name"],
            "color": space_cfg.get("color", ""),
        }
        if space_cfg.get("lists"):
            entry["lists"] = {
                lk: list_ids[space_key].get(lk, "") for lk in space_cfg["lists"]
            }
        if space_cfg.get("folders"):
            entry["folders"] = {}
            for fk, fcfg in space_cfg["folders"].items():
                entry["folders"][fk] = {
                    "id": folder_ids[space_key].get(fk, ""),
                    "lists": {lk: list_ids[space_key].get(lk, "") for lk in fcfg.get("lists", {})}
                }
        id_map["spaces"][space_key] = entry

    return id_map


# ---------------------------------------------------------------------------
# YAML writer (no external deps needed for output)
# ---------------------------------------------------------------------------

def write_ids_yaml(data: dict, path: str) -> None:
    lines = [
        "# boot-clickup — Generated ID Index",
        "# Source of truth for all automation scripts.",
        "# Do NOT edit manually — re-run setup.py to regenerate.",
        "# Re-running setup.py with --output will overwrite this file.",
        "",
    ]

    def emit(obj: dict, indent: int = 0) -> None:
        pad = "  " * indent
        for k, v in obj.items():
            if isinstance(v, dict):
                lines.append(f"{pad}{k}:")
                emit(v, indent + 1)
            else:
                lines.append(f"{pad}{k}: '{v}'")

    emit(data)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  ID index → {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Personal Life OS in ClickUp from config.yaml.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  export CLICKUP_API_KEY=pk_xxxxx
  python setup.py                          # full setup
  python setup.py --dry-run                # preview only
  python setup.py --config my_config.yaml  # custom config
  python setup.py --output my_ids.yaml     # custom output path

Get your API token:
  ClickUp → Settings (avatar, bottom-left) → Apps → API Token
        """
    )
    parser.add_argument("--api-key", "-k",
                        default=os.environ.get("CLICKUP_API_KEY", ""),
                        help="ClickUp personal API token (or set CLICKUP_API_KEY env var)")
    parser.add_argument("--config", "-c", default="config.yaml",
                        help="Path to config YAML file (default: config.yaml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print all API calls without executing them")
    parser.add_argument("--output", "-o", default="clickup_ids.yaml",
                        help="Output file for generated IDs (default: clickup_ids.yaml)")
    args = parser.parse_args()

    # Validate
    if not os.path.exists(args.config):
        print(f"ERROR: Config file not found: {args.config}")
        print(f"  Copy config.yaml from the repo and customize it.")
        sys.exit(1)

    if not args.api_key and not args.dry_run:
        print("ERROR: No API key provided.")
        print("  Set CLICKUP_API_KEY environment variable or pass --api-key pk_xxxxx")
        print("  Get your token: ClickUp → Settings → Apps → API Token")
        sys.exit(1)

    # Load config
    cfg = load_yaml(args.config)
    if args.dry_run:
        print(f"[DRY RUN] Config loaded from {args.config}")
        print(f"[DRY RUN] Spaces to create: {list(cfg.get('spaces', {}).keys())}\n")

    # Build
    api = ClickUpAPI(api_key=args.api_key, dry_run=args.dry_run)
    try:
        ids = build(api, cfg)
    except (ValueError, KeyError) as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    # Write output
    write_ids_yaml(ids, args.output)

    print("\n✅ Setup complete!")
    print(f"   API calls made: {api._call_count}")
    print(f"   ID index: {args.output}")

    # Print manual steps from config
    favorites = cfg.get("favorites_setup_order", [])
    if favorites:
        print("\n── Manual UI steps (ClickUp app, ~20 min) ──────────────────────")
        print("\n1. Configure Favorites bar (morning review order):")
        for fav in favorites:
            print(f"     • {fav}")
        print("\n2. Save a list as template:")
        print("     Open WORK / Personal Ops → right-click list → Save as Template")
        print('     Name it "Standard Work List" → use for all new engagement/project lists')
        print("\n3. Gantt preferences (per user, can\'t be set via API):")
        print("     Open any Gantt view → gear icon → uncheck 'Show weekends'")
        print("\n4. Automations (Unlimited plan):")
        print("     FAMILY / KIDS EVENTS: task created → set priority = Urgent")
        print("     CAREER / ACTIVE APPLICATIONS: status = Rejected → move to JD ARCHIVE")
        print("     PROJECTS / ACTIVE: status = Shipped → move to ARCHIVE")
        print("     INBOX / 03 TRIAGE: task created → assign to me")
        print()


if __name__ == "__main__":
    main()
