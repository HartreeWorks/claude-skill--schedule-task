---
name: schedule-task
description: This skill should be used when the user asks to schedule tasks, set up cron jobs, manage launchd agents, list scheduled tasks, check what's scheduled, or asks when/what time a task is scheduled to run. For running Claude commands on a schedule.
---

# Scheduled Task Manager

Manage scheduled tasks on macOS using launchd LaunchAgents. This skill creates, lists, edits, and removes scheduled tasks while maintaining a registry of tasks it manages.

## How It Works

- Uses macOS **launchd** (the native, reliable scheduler)
- Stores plist files in `~/Library/LaunchAgents/`
- Maintains a registry at `~/.claude/skills/schedule-task/registry.json` to track only tasks created by this skill
- All task labels are prefixed with `com.claude.scheduled.` for easy identification
- **Dual-machine support**: Tasks can run on either MacBook (`mbp`) or Mac Mini (`mini`), with a shared registry synced via Syncthing

## Dual-Machine Setup

Tasks can be scheduled to run on either machine:

| Machine | Use for | Examples |
|---------|---------|----------|
| `mini` | Long-running tasks, always-on reliability | Claude skills, transcription, AI agents |
| `mbp` | MacBook-specific tasks | Firewall checks, activity tracking, display-dependent tasks |

**Default behaviour:**
- Tasks are created on the **current machine** by default
- Use `--machine mini` or `--machine mbp` to specify a different machine
- The `list` command shows all tasks across both machines with their status

**Creating tasks on a specific machine:**

```bash
# Create on Mac Mini (from either machine)
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "overnight-task" \
  --command "claude --dangerously-skip-permissions -p '/some-skill'" \
  --machine mini \
  --hour 3 --minute 0

# Create on MacBook
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "macbook-check" \
  --command "/path/to/script.sh" \
  --machine mbp \
  --interval 3600
```

**Status meanings in `list` output:**
- `active` — Task is loaded and running on this machine
- `remote` — Task runs on the other machine (enabled in registry)
- `disabled` — Task is disabled
- `unloaded` — Task should be running locally but plist isn't loaded

## Usage

### Schedule a New Task

Use the Python script to create a scheduled task:

```bash
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "daily-hello" \
  --command "claude --dangerously-skip-permissions -p 'Hello'" \
  --hour 9 \
  --minute 0
```

**Options for scheduling:**

| Option | Description | Example |
|--------|-------------|---------|
| `--machine` | Machine to run on (`mbp` or `mini`) | `--machine mini` |
| `--hour` | Hour (0-23) | `--hour 9` |
| `--minute` | Minute (0-59) | `--minute 30` |
| `--weekday` | Day of week (0=Sun, 1=Mon, ..., 6=Sat) | `--weekday 1` |
| `--day` | Day of month (1-31) | `--day 15` |
| `--interval` | Run every N seconds | `--interval 3600` |

**Examples:**

```bash
# Every day at 9:00 AM - run a Claude skill
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "morning-briefing" \
  --command "claude --dangerously-skip-permissions -p '/chief-of-staff'" \
  --hour 9 --minute 0

# Every Monday at 10:00 AM
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "weekly-review" \
  --command "claude --dangerously-skip-permissions -p 'Time for weekly review'" \
  --hour 10 --minute 0 --weekday 1

# Every hour - non-Claude command (no flag needed)
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "hourly-check" \
  --command "/path/to/script.sh" \
  --interval 3600
```

### List All Scheduled Tasks

```bash
python ~/.claude/skills/schedule-task/scripts/scheduler.py list
```

Shows all tasks managed by this skill with their schedules and status.

### View Task Details

```bash
python ~/.claude/skills/schedule-task/scripts/scheduler.py show --name "daily-hello"
```

### Remove a Task

```bash
python ~/.claude/skills/schedule-task/scripts/scheduler.py remove --name "daily-hello"
```

### Disable/Enable a Task

```bash
# Disable (unload but keep configuration)
python ~/.claude/skills/schedule-task/scripts/scheduler.py disable --name "daily-hello"

# Enable (reload)
python ~/.claude/skills/schedule-task/scripts/scheduler.py enable --name "daily-hello"
```

### Edit a Task

```bash
# Change the schedule
python ~/.claude/skills/schedule-task/scripts/scheduler.py edit \
  --name "daily-hello" \
  --hour 10 --minute 30

# Change the command
python ~/.claude/skills/schedule-task/scripts/scheduler.py edit \
  --name "daily-hello" \
  --command "claude --dangerously-skip-permissions -p 'New message'"
```

### View Logs

Each task logs to `/tmp/claude-scheduled-<name>.log`. View logs with:

```bash
python ~/.claude/skills/schedule-task/scripts/scheduler.py logs --name "daily-hello"
```

## Registry Format

The registry at `~/.claude/skills/schedule-task/registry.json` tracks all managed tasks across both machines (synced via Syncthing):

```json
{
  "tasks": {
    "daily-hello": {
      "name": "daily-hello",
      "command": "claude --dangerously-skip-permissions -p 'Hello'",
      "schedule": {
        "hour": 9,
        "minute": 0
      },
      "created": "2024-12-23T09:00:00",
      "enabled": true,
      "plist_path": "~/Library/LaunchAgents/com.claude.scheduled.daily-hello.plist",
      "machine": "mini"
    }
  }
}
```

The `machine` field indicates where the task runs (`mbp` or `mini`). The plist file only exists on the target machine.

## Important Notes

1. **Use `--dangerously-skip-permissions` for autonomous execution**: Scheduled Claude tasks must include this flag to run without permission prompts. Without it, macOS will show permission dialogs that block execution.
   - ✅ `claude --dangerously-skip-permissions -p '/chief-of-staff'`
   - ❌ `claude -p '/chief-of-staff'` (will prompt for permissions and fail)

2. **Use `-p` flag**: For scheduled Claude commands, always use `claude -p "prompt"` (print mode) for non-interactive execution

3. **Use exact skill names, not aliases**: When scheduling a skill with `-p '/skill-name'`, you must use the exact skill name from the skill's `name:` field, not aliases. Aliases like `/cos` for `/chief-of-staff` only work in interactive mode.
   - ✅ `claude --dangerously-skip-permissions -p '/chief-of-staff'`
   - ❌ `claude --dangerously-skip-permissions -p '/cos'` (alias won't work)

   The scheduler validates this and will suggest the correct name if you use an alias.

4. **Full paths**: The script automatically resolves the full path to `claude` binary

5. **Logs**: Check `/tmp/claude-scheduled-<name>.log` and `.err` for output and errors

6. **Missed runs**: launchd will run missed jobs when the Mac wakes from sleep (if the job was due during sleep)

7. **Persistence**: Tasks survive reboots. They're loaded automatically from `~/Library/LaunchAgents/`

## Workflow

When user asks to schedule something:

1. **Clarify the schedule**: What time/interval? Daily, weekly, specific days?
2. **Clarify the command**: What should run? Ensure it works non-interactively
3. **Create the task**: Use the scheduler.py script
4. **Confirm creation**: Show the user the task details and log location
5. **Test if needed**: Optionally run the command manually to verify it works

## Troubleshooting

**Task not running:**
```bash
# Check if loaded
launchctl list | grep com.claude.scheduled

# Check for errors in system log
log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 1h | grep claude
```

**Permission dialogs appearing:**
If you see dialogs like "X.X.X would like to access files in your Documents folder":
- Ensure the command includes `--dangerously-skip-permissions` flag
- Edit the task: `python scheduler.py edit --name "task-name" --command "claude --dangerously-skip-permissions -p '...'"`

**Debugging:**
```bash
# Manually load a plist to see errors
launchctl load ~/Library/LaunchAgents/com.claude.scheduled.task-name.plist

# Check the error log
cat /tmp/claude-scheduled-task-name.err

# Test run a task
python ~/.claude/skills/schedule-task/scripts/scheduler.py run --name "task-name"
```


## Update check

This skill is managed by [skills.sh](https://skills.sh). To check for updates, run `npx skills update`.

