# Agent Backup

**Universal AI Agent Backup & Restore Tool**

[![Version](https://img.shields.io/github/v/release/praveenkay/agent-backup?sort=semver)](https://github.com/praveenkay/agent-backup/releases)
[![License](https://img.shields.io/github/license/praveenkay/agent-backup)](https://github.com/praveenkay/agent-backup/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)

> Never lose your AI agent configuration again. One-command backup and restore for Hermes, Claude Code, Codex, OpenCode, and any agent with a config directory.

---

## Features

- **One-command backup** — Single command backs up your entire agent configuration
- **Smart compression** — Auto-selected `zstd` (3x faster than gzip, similar ratio)
- **Manifest verification** — Every backup includes a JSON manifest for integrity
- **Telegram bot** — Trigger backups remotely via Telegram
- **Scheduled backups** — Cron-based daily/weekly/monthly/custom scheduling
- **Multi-agent support** — Hermes, Claude Code, Codex, OpenCode + custom configurations
- **Selective restore** — Granular control over what to restore
- **Cross-platform** — macOS, Linux, Windows (WSL)

---

## Supported Agents

| Agent | Config Dir | Auto-Detect | Status |
|-------|-----------|-------------|--------|
| **Hermes Agent** | `~/.hermes` | Automatic | Stable |
| **Claude Code** | `~/.claude` | Automatic | Beta |
| **OpenAI Codex** | `~/.codex` | Automatic | Beta |
| **OpenCode** | `~/.opencode` | Automatic | Beta |
| **Custom** | Any path | Manual | Stable |

---

## Quick Start

### 1. Install

```bash
# Via pip
pip install agent-backup

# Latest from source
pip install git+https://github.com/praveenkay/agent-backup.git
```

### 2. Backup

```bash
# Auto-detect agent and backup
agent-backup backup --to ~/backups

# Specific agent with full options
agent-backup backup --agent hermes --to ~/backups --compression zst --no-logs

# Dry run to preview
agent-backup backup --to ~/backups --dry-run
```

### 3. Restore

```bash
# Restore to original location
agent-backup restore --from ~/backups/hermes-*-20260503.tar.zst --to ~/.hermes

# Restore to new machine
agent-backup restore --from backup.tar.zst --to ~/.hermes
```

### 4. Schedule

```bash
# Daily at 2 AM
agent-backup schedule --agent hermes --frequency daily --time 02:00 --to ~/backups

# Weekly on Sundays at 3 AM
agent-backup schedule --agent hermes --frequency weekly --time 03:00 --to ~/backups

# Custom cron expression
agent-backup schedule --agent hermes --frequency custom --to ~/backups
# Enter: 0 */6 * * *(every 6 hours)
```

### 5. Telegram Bot

```bash
# Configure your bot
agent-backup telegram-bot --token 123456:ABC-DEF1234ghIkl

# Start the bot (run in background)
nohup agent-backup-bot &

# Or use systemd (Linux)
sudo tee /etc/systemd/system/agent-backup-bot.service << 'EOF'
[Unit]
Description=Agent Backup Telegram Bot
After=network.target

[Service]
Type=simple
User=%I
ExecStart=/usr/local/bin/agent-backup-bot
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now agent-backup-bot
```

**Telegram Commands:**
- `/start` — Show welcome message
- `/backup` — Trigger backup now (returns archive file)
- `/restore` — Get latest backup file download link
- `/list` — List recent backups
- `/status` — Check agent status and size
- `/help` — Show all commands

---

## CLI Reference

### Commands

| Command | Description |
|---------|-------------|
| `backup` | Create a backup archive |
| `restore` | Restore from backup archive |
| `list` | List available backups |
| `schedule` | Setup automatic backup schedule |
| `unschedule` | Remove backup schedule |
| `schedules` | List all backup schedules |
| `telegram-bot` | Configure Telegram bot |
| `status` | Check agent status and last backup |

### Backup Options

```
agent-backup backup [OPTIONS]

Options:
  --agent       Agent framework (auto, hermes, claude-code, codex, opencode) [default: auto]
  --to          Backup destination directory (required)
  --compression Compression format (auto, zst, gz, bz2, xz, none) [default: auto]
  --encrypt     Encrypt backup with GPG [not yet implemented]
  --no-sessions Exclude session history (reduces size)
  --no-logs     Exclude log files (reduces size)
  --exclude     Additional patterns to exclude
  --quiet       Minimal output
  --dry-run     Preview without creating archive
```

### Restore Options

```
agent-backup restore [OPTIONS]

Options:
  --from     Backup archive path (required)
  --to       Restore target directory [default: ~/.hermes]
  --verify   Verify manifest after restore [default: true]
  --dry-run  Preview without restoring
```

---

## Backup Structure

```
backups/
├── hermes-Mac-Mini-20260503-141200.tar.zst          # Compressed archive
├── hermes-Mac-Mini-20260503-141200.tar.zst.manifest.json
└── claude-Mac-Mini-20260503-141300.tar.zst
```

### Manifest Format

```json
{
  "agent-backup": {
    "version": "1.0.0",
    "created_at": "2026-05-03T14:12:00Z",
    "agent": {
      "id": "hermes",
      "name": "Hermes Agent",
      "hostname": "Mac-Mini.local",
      "platform": "darwin"
    },
    "backup": {
      "format": "tar.zst",
      "algorithm": "zstd-fast",
      "items_backed_up": 19,
      "paths": [".hermes/config.yaml", ...]
    },
    "restore_instructions": {
      "method": "agent-backup restore",
      "example": "agent-backup restore --from archive.tar.zst --to ~/.hermes"
    }
  }
}
```

---

## Hermes-Specific Notes

### What's Backed Up (Critical)

| Category | Items |
|----------|-------|
| **Config** | `config.yaml`, `auth.json`, `.env`, `SOUL.md` |
| **State** | `kanban.db`, `gateway.db`, `gateway_state.json`, `channel_directory.json` |
| **Skills** | `skills/` (all custom skills) |
| **Memory** | `memories/MEMORY.md`, `memories/USER.md` |
| **Automation** | `cron/`, `scripts/`, `hooks/` |
| **Checkpoints** | `checkpoints/`, `state-snapshots/` |
| **Source Code** | `hermes-agent/`, `webui/` |

### What's Excluded by Default

| Category | Reason |
|----------|--------|
| `sessions/` | Large conversation history (use `--no-sessions` to skip) |
| `logs/` | Easily regenerated (use `--no-logs` to skip) |
| `cache/` | Temporary cached data |
| `image_cache/`, `audio_cache/` | Generated media |
| `*.pyc`, `__pycache__`, `node_modules/` | Generated code |

### Restore to New Machine

```bash
# 1. Install Hermes on new machine (or ensure target dir exists)
mkdir -p ~/.hermes

# 2. Restore backup
agent-backup restore --from backup.tar.zst --to ~/.hermes

# 3. Verify
ls ~/.hermes/config.yaml ~/.hermes/skills ~/.hermes/memories

# 4. Restart Hermes
hermes start
```

---

## Custom Agent Configuration

You can backup any agent by creating a custom configuration file:

```yaml
# ~/.agent-backup/custom-agents.yaml
custom_agents:
  my-custom-agent:
    config_dir: ~/.myagent
    critical_files:
      - config.yaml
      - auth.json
    critical_dirs:
      - data
      - plugins
    optional_dirs:
      - cache
    exclude_patterns:
      - "*.log"
      - "temp/"
```

Then use: `agent-backup backup --agent my-custom-agent --to ~/backups`

---

## Automation Examples

### Daily Backup via Cron

```bash
# Add to crontab (auto-installed by `agent-backup schedule`)
0 2 * * * agent-backup backup --agent hermes --to ~/backups --no-logs --quiet >> ~/.agent-backup/backup.log 2>&1
```

### Pre-Update Safety Backup

```bash
#!/bin/bash
# save as ~/.hermes/hooks/pre-update
backup_path="$HOME/backups/hermes-pre-update-$(date +%Y%m%d-%H%M%S).tar.zst"
agent-backup backup --agent hermes --to "$backup_path" --quiet
```

### Cloud Upload (AWS S3)

```bash
#!/bin/bash
# Backup then upload to S3
backup=$(agent-backup backup --agent hermes --to /tmp 2>&1 | grep "Archive:" | awk '{print $2}')
aws s3 cp "$backup" s3://my-agent-backups/
aws s3 cp "${backup}.manifest.json" s3://my-agent-backups/
```

### Health Check with Telegram Alerts

```bash
#!/bin/bash
if ! agent-backup status --agent hermes | grep -q "Exists: ✅"; then
  curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    -d "chat_id=$CHAT_ID" \
    -d "text=⚠️ Agent backup check FAILED for hermes"
fi
```

---

## Troubleshooting

### zstd not installed

```bash
# macOS
brew install zstd

# Ubuntu/Debian
sudo apt-get install zstd

# Fallback: tool auto-falls back to gzip
```

### Permission denied on restore

```bash
# Fix ownership
sudo chown -R $(whoami) ~/.hermes
chmod -R u+rw ~/.hermes
```

### Backup too large

```bash
# Exclude sessions and logs
agent-backup backup --agent hermes --to ~/backups --no-sessions --no-logs

# Check sizes
agent-backup status --agent hermes
```

### Cron job not running

```bash
# Check cron is installed and running
which crontab
# macOS: Grant Full Disk Access to cron in System Preferences

# Verify job installed
crontab -l | grep agent-backup
```

---

## Development

```bash
# Clone and setup
git clone https://github.com/praveenkay/agent-backup.git
cd agent-backup
pip install -e ".[dev]"

# Run tests
pytest tests/

# Lint
black src/
ruff check src/

# Build
python -m build
```

---

## Changelog

### v1.0.0 — 2026-05-03
- Initial release
- Hermes, Claude Code, Codex, OpenCode support
- zstd compression with automatic fallback
- Telegram bot integration
- Cron-based scheduling
- Manifest generation and verification

---

## License

MIT — See [LICENSE](LICENSE)

## Contributing

PRs welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Support

- [GitHub Issues](https://github.com/praveenkay/agent-backup/issues)
- [Releases](https://github.com/praveenkay/agent-backup/releases)

---

**Made with care for the AI agent community.**
