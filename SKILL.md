---
name: schedule-task
description: This skill should be used when the user asks to "schedule a task", "run something daily", "set up a cron job", "schedule a command", "list scheduled tasks", "manage scheduled tasks", "remove a scheduled task", "edit a scheduled task", or mentions running Claude commands on a schedule. Manages macOS launchd LaunchAgents for scheduled command execution.
---

# Scheduled Task Manager

Manage scheduled tasks on macOS using launchd LaunchAgents. This skill creates, lists, edits, and removes scheduled tasks while maintaining a registry of tasks it manages.

## How It Works

- Uses macOS **launchd** (the native, reliable scheduler)
- Stores plist files in `~/Library/LaunchAgents/`
- Maintains a registry at `~/.claude/skills/schedule-task/registry.json` to track only tasks created by this skill
- All task labels are prefixed with `com.claude.scheduled.` for easy identification

## Usage

### Schedule a New Task

Use the Python script to create a scheduled task:

```bash
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "daily-hello" \
  --command "claude -p 'Hello'" \
  --hour 9 \
  --minute 0
```

**Options for scheduling:**

| Option | Description | Example |
|--------|-------------|---------|
| `--hour` | Hour (0-23) | `--hour 9` |
| `--minute` | Minute (0-59) | `--minute 30` |
| `--weekday` | Day of week (0=Sun, 1=Mon, ..., 6=Sat) | `--weekday 1` |
| `--day` | Day of month (1-31) | `--day 15` |
| `--interval` | Run every N seconds | `--interval 3600` |

**Examples:**

```bash
# Every day at 9:00 AM
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "morning-task" \
  --command "claude -p 'Good morning'" \
  --hour 9 --minute 0

# Every Monday at 10:00 AM
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "weekly-review" \
  --command "claude -p 'Time for weekly review'" \
  --hour 10 --minute 0 --weekday 1

# Every hour
python ~/.claude/skills/schedule-task/scripts/scheduler.py create \
  --name "hourly-check" \
  --command "claude -p 'Hourly check'" \
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
  --command "claude -p 'New message'"
```

### View Logs

Each task logs to `/tmp/claude-scheduled-<name>.log`. View logs with:

```bash
python ~/.claude/skills/schedule-task/scripts/scheduler.py logs --name "daily-hello"
```

## Registry Format

The registry at `~/.claude/skills/schedule-task/registry.json` tracks all managed tasks:

```json
{
  "tasks": {
    "daily-hello": {
      "name": "daily-hello",
      "command": "claude -p 'Hello'",
      "schedule": {
        "hour": 9,
        "minute": 0
      },
      "created": "2024-12-23T09:00:00",
      "enabled": true,
      "plist_path": "~/Library/LaunchAgents/com.claude.scheduled.daily-hello.plist"
    }
  }
}
```

## Important Notes

1. **Use `-p` flag**: For scheduled Claude commands, always use `claude -p "prompt"` (print mode) for non-interactive execution

2. **Full paths**: The script automatically resolves the full path to `claude` binary

3. **Logs**: Check `/tmp/claude-scheduled-<name>.log` and `.err` for output and errors

4. **Missed runs**: launchd will run missed jobs when the Mac wakes from sleep (if the job was due during sleep)

5. **Persistence**: Tasks survive reboots. They're loaded automatically from `~/Library/LaunchAgents/`

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

**Permission issues:**
- Ensure the command has the right permissions
- Check that the claude binary path is correct

**Debugging:**
```bash
# Manually load a plist to see errors
launchctl load ~/Library/LaunchAgents/com.claude.scheduled.task-name.plist

# Check the error log
cat /tmp/claude-scheduled-task-name.err
```
