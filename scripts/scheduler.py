#!/usr/bin/env python3
"""
Scheduled Task Manager for macOS using launchd.
Manages LaunchAgents and maintains a registry of created tasks.
"""

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Paths
SKILL_DIR = Path(__file__).parent.parent
REGISTRY_PATH = SKILL_DIR / "registry.json"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL_PREFIX = "com.claude.scheduled."
LOG_DIR = Path("/tmp")


def load_registry() -> dict:
    """Load the task registry from disk."""
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, "r") as f:
            return json.load(f)
    return {"tasks": {}}


def save_registry(registry: dict) -> None:
    """Save the task registry to disk."""
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, default=str)


def get_claude_path() -> str:
    """Find the full path to the claude binary."""
    result = subprocess.run(["which", "claude"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    # Common locations
    common_paths = [
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
        str(Path.home() / ".local" / "bin" / "claude"),
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    raise RuntimeError("Could not find claude binary. Please ensure it's installed and in PATH.")


def get_plist_path(name: str) -> Path:
    """Get the plist file path for a task."""
    return LAUNCH_AGENTS_DIR / f"{LABEL_PREFIX}{name}.plist"


def get_label(name: str) -> str:
    """Get the launchd label for a task."""
    return f"{LABEL_PREFIX}{name}"


def build_plist(name: str, command: str, schedule: dict) -> dict:
    """Build a launchd plist dictionary."""
    # Parse the command - handle shell commands properly
    label = get_label(name)
    log_path = LOG_DIR / f"claude-scheduled-{name}.log"
    err_path = LOG_DIR / f"claude-scheduled-{name}.err"

    plist = {
        "Label": label,
        "ProgramArguments": ["/bin/bash", "-c", command],
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(err_path),
        "RunAtLoad": False,
    }

    # Add schedule
    if "interval" in schedule:
        plist["StartInterval"] = schedule["interval"]
    else:
        calendar_interval = {}
        if "hour" in schedule:
            calendar_interval["Hour"] = schedule["hour"]
        if "minute" in schedule:
            calendar_interval["Minute"] = schedule["minute"]
        if "weekday" in schedule:
            calendar_interval["Weekday"] = schedule["weekday"]
        if "day" in schedule:
            calendar_interval["Day"] = schedule["day"]
        if calendar_interval:
            plist["StartCalendarInterval"] = calendar_interval

    return plist


def create_task(args) -> None:
    """Create a new scheduled task."""
    name = args.name
    command = args.command

    # Validate name
    if not name or "/" in name or " " in name:
        print(f"Error: Invalid task name '{name}'. Use alphanumeric characters, dashes, and underscores only.")
        sys.exit(1)

    # Check if task already exists
    registry = load_registry()
    if name in registry["tasks"]:
        print(f"Error: Task '{name}' already exists. Use 'edit' to modify or 'remove' first.")
        sys.exit(1)

    # Build schedule
    schedule = {}
    if args.interval:
        schedule["interval"] = args.interval
    else:
        if args.hour is not None:
            schedule["hour"] = args.hour
        if args.minute is not None:
            schedule["minute"] = args.minute
        if args.weekday is not None:
            schedule["weekday"] = args.weekday
        if args.day is not None:
            schedule["day"] = args.day

    if not schedule:
        print("Error: Must specify a schedule (--hour/--minute, --interval, --weekday, or --day)")
        sys.exit(1)

    # Ensure LaunchAgents directory exists
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    # Create plist
    plist = build_plist(name, command, schedule)
    plist_path = get_plist_path(name)

    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)

    # Load the task
    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Warning: Failed to load task: {result.stderr}")

    # Update registry
    registry["tasks"][name] = {
        "name": name,
        "command": command,
        "schedule": schedule,
        "created": datetime.now().isoformat(),
        "enabled": True,
        "plist_path": str(plist_path),
    }
    save_registry(registry)

    print(f"Created scheduled task '{name}'")
    print(f"  Command: {command}")
    print(f"  Schedule: {format_schedule(schedule)}")
    print(f"  Logs: /tmp/claude-scheduled-{name}.log")


def list_tasks(args) -> None:
    """List all scheduled tasks."""
    registry = load_registry()
    tasks = registry.get("tasks", {})

    if not tasks:
        print("No scheduled tasks found.")
        return

    # Check which tasks are actually loaded
    result = subprocess.run(
        ["launchctl", "list"],
        capture_output=True,
        text=True
    )
    loaded_labels = set(result.stdout.split())

    print(f"{'Name':<25} {'Schedule':<30} {'Status':<10} {'Command'}")
    print("-" * 100)

    for name, task in tasks.items():
        label = get_label(name)
        is_loaded = label in loaded_labels
        status = "active" if is_loaded else ("disabled" if not task.get("enabled", True) else "unloaded")
        schedule_str = format_schedule(task.get("schedule", {}))
        command = task.get("command", "")
        # Truncate command if too long
        if len(command) > 40:
            command = command[:37] + "..."
        print(f"{name:<25} {schedule_str:<30} {status:<10} {command}")


def format_schedule(schedule: dict) -> str:
    """Format a schedule dict into a human-readable string."""
    if "interval" in schedule:
        interval = schedule["interval"]
        if interval >= 86400:
            return f"every {interval // 86400} day(s)"
        elif interval >= 3600:
            return f"every {interval // 3600} hour(s)"
        elif interval >= 60:
            return f"every {interval // 60} minute(s)"
        else:
            return f"every {interval} second(s)"

    parts = []
    if "weekday" in schedule:
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        parts.append(days[schedule["weekday"]])
    if "day" in schedule:
        parts.append(f"day {schedule['day']}")

    time_parts = []
    if "hour" in schedule:
        time_parts.append(f"{schedule['hour']:02d}")
    else:
        time_parts.append("*")
    if "minute" in schedule:
        time_parts.append(f"{schedule['minute']:02d}")
    else:
        time_parts.append("00")

    time_str = ":".join(time_parts)

    if parts:
        return f"{', '.join(parts)} at {time_str}"
    else:
        return f"daily at {time_str}"


def show_task(args) -> None:
    """Show details of a specific task."""
    name = args.name
    registry = load_registry()

    if name not in registry["tasks"]:
        print(f"Error: Task '{name}' not found.")
        sys.exit(1)

    task = registry["tasks"][name]

    # Check if loaded
    result = subprocess.run(
        ["launchctl", "list", get_label(name)],
        capture_output=True,
        text=True
    )
    is_loaded = result.returncode == 0

    print(f"Task: {name}")
    print(f"  Command:  {task.get('command', 'N/A')}")
    print(f"  Schedule: {format_schedule(task.get('schedule', {}))}")
    print(f"  Status:   {'active' if is_loaded else 'not loaded'}")
    print(f"  Enabled:  {task.get('enabled', True)}")
    print(f"  Created:  {task.get('created', 'N/A')}")
    print(f"  Plist:    {task.get('plist_path', 'N/A')}")
    print(f"  Log:      /tmp/claude-scheduled-{name}.log")
    print(f"  Errors:   /tmp/claude-scheduled-{name}.err")


def remove_task(args) -> None:
    """Remove a scheduled task."""
    name = args.name
    registry = load_registry()

    if name not in registry["tasks"]:
        print(f"Error: Task '{name}' not found in registry.")
        sys.exit(1)

    # Unload first
    plist_path = get_plist_path(name)
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True
        )
        plist_path.unlink()

    # Remove from registry
    del registry["tasks"][name]
    save_registry(registry)

    print(f"Removed scheduled task '{name}'")


def disable_task(args) -> None:
    """Disable a scheduled task (unload but keep config)."""
    name = args.name
    registry = load_registry()

    if name not in registry["tasks"]:
        print(f"Error: Task '{name}' not found.")
        sys.exit(1)

    plist_path = get_plist_path(name)
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True
        )

    registry["tasks"][name]["enabled"] = False
    save_registry(registry)

    print(f"Disabled task '{name}'")


def enable_task(args) -> None:
    """Enable a scheduled task."""
    name = args.name
    registry = load_registry()

    if name not in registry["tasks"]:
        print(f"Error: Task '{name}' not found.")
        sys.exit(1)

    plist_path = get_plist_path(name)
    if plist_path.exists():
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Warning: Failed to load task: {result.stderr}")

    registry["tasks"][name]["enabled"] = True
    save_registry(registry)

    print(f"Enabled task '{name}'")


def edit_task(args) -> None:
    """Edit an existing scheduled task."""
    name = args.name
    registry = load_registry()

    if name not in registry["tasks"]:
        print(f"Error: Task '{name}' not found.")
        sys.exit(1)

    task = registry["tasks"][name]

    # Update command if provided
    if args.command:
        task["command"] = args.command

    # Update schedule if any schedule args provided
    schedule = task.get("schedule", {})
    if args.interval is not None:
        schedule = {"interval": args.interval}
    else:
        if args.hour is not None:
            schedule["hour"] = args.hour
            schedule.pop("interval", None)
        if args.minute is not None:
            schedule["minute"] = args.minute
            schedule.pop("interval", None)
        if args.weekday is not None:
            schedule["weekday"] = args.weekday
            schedule.pop("interval", None)
        if args.day is not None:
            schedule["day"] = args.day
            schedule.pop("interval", None)

    task["schedule"] = schedule

    # Unload old plist
    plist_path = get_plist_path(name)
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True
        )

    # Create new plist
    plist = build_plist(name, task["command"], schedule)
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)

    # Reload if enabled
    if task.get("enabled", True):
        subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True
        )

    task["modified"] = datetime.now().isoformat()
    save_registry(registry)

    print(f"Updated task '{name}'")
    print(f"  Command: {task['command']}")
    print(f"  Schedule: {format_schedule(schedule)}")


def show_logs(args) -> None:
    """Show logs for a task."""
    name = args.name
    log_path = LOG_DIR / f"claude-scheduled-{name}.log"
    err_path = LOG_DIR / f"claude-scheduled-{name}.err"

    lines = args.lines or 50

    print(f"=== Stdout ({log_path}) ===")
    if log_path.exists():
        with open(log_path, "r") as f:
            content = f.readlines()
            for line in content[-lines:]:
                print(line.rstrip())
    else:
        print("(no log file yet)")

    print(f"\n=== Stderr ({err_path}) ===")
    if err_path.exists():
        with open(err_path, "r") as f:
            content = f.readlines()
            for line in content[-lines:]:
                print(line.rstrip())
    else:
        print("(no error file yet)")


def run_now(args) -> None:
    """Manually trigger a task to run immediately."""
    name = args.name
    registry = load_registry()

    if name not in registry["tasks"]:
        print(f"Error: Task '{name}' not found.")
        sys.exit(1)

    label = get_label(name)
    result = subprocess.run(
        ["launchctl", "start", label],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Error: Failed to start task: {result.stderr}")
        sys.exit(1)

    print(f"Triggered task '{name}' to run now")
    print(f"Check logs at: /tmp/claude-scheduled-{name}.log")


def main():
    parser = argparse.ArgumentParser(description="Manage scheduled Claude tasks")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Create
    create_parser = subparsers.add_parser("create", help="Create a new scheduled task")
    create_parser.add_argument("--name", required=True, help="Unique name for the task")
    create_parser.add_argument("--command", required=True, help="Command to run")
    create_parser.add_argument("--hour", type=int, help="Hour (0-23)")
    create_parser.add_argument("--minute", type=int, help="Minute (0-59)")
    create_parser.add_argument("--weekday", type=int, help="Day of week (0=Sun, 6=Sat)")
    create_parser.add_argument("--day", type=int, help="Day of month (1-31)")
    create_parser.add_argument("--interval", type=int, help="Run every N seconds")
    create_parser.set_defaults(func=create_task)

    # List
    list_parser = subparsers.add_parser("list", help="List all scheduled tasks")
    list_parser.set_defaults(func=list_tasks)

    # Show
    show_parser = subparsers.add_parser("show", help="Show task details")
    show_parser.add_argument("--name", required=True, help="Task name")
    show_parser.set_defaults(func=show_task)

    # Remove
    remove_parser = subparsers.add_parser("remove", help="Remove a scheduled task")
    remove_parser.add_argument("--name", required=True, help="Task name")
    remove_parser.set_defaults(func=remove_task)

    # Disable
    disable_parser = subparsers.add_parser("disable", help="Disable a task")
    disable_parser.add_argument("--name", required=True, help="Task name")
    disable_parser.set_defaults(func=disable_task)

    # Enable
    enable_parser = subparsers.add_parser("enable", help="Enable a task")
    enable_parser.add_argument("--name", required=True, help="Task name")
    enable_parser.set_defaults(func=enable_task)

    # Edit
    edit_parser = subparsers.add_parser("edit", help="Edit a task")
    edit_parser.add_argument("--name", required=True, help="Task name")
    edit_parser.add_argument("--command", help="New command")
    edit_parser.add_argument("--hour", type=int, help="Hour (0-23)")
    edit_parser.add_argument("--minute", type=int, help="Minute (0-59)")
    edit_parser.add_argument("--weekday", type=int, help="Day of week (0=Sun, 6=Sat)")
    edit_parser.add_argument("--day", type=int, help="Day of month (1-31)")
    edit_parser.add_argument("--interval", type=int, help="Run every N seconds")
    edit_parser.set_defaults(func=edit_task)

    # Logs
    logs_parser = subparsers.add_parser("logs", help="Show task logs")
    logs_parser.add_argument("--name", required=True, help="Task name")
    logs_parser.add_argument("--lines", type=int, default=50, help="Number of lines to show")
    logs_parser.set_defaults(func=show_logs)

    # Run now
    run_parser = subparsers.add_parser("run", help="Run a task immediately")
    run_parser.add_argument("--name", required=True, help="Task name")
    run_parser.set_defaults(func=run_now)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
