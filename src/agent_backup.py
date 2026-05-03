#!/usr/bin/env python3
"""
agent-backup — Universal AI Agent Backup & Restore Tool
Supports: Hermes, Claude Code, Codex, OpenCode, and any agent with a config dir

Usage:
    agent-backup backup --agent hermes --to /backup/path
    agent-backup restore --from /backup/path --to ~/.hermes
    agent-backup list --from /backup/path
    agent-backup schedule --agent hermes --frequency daily
    agent-backup telegram-bot --token YOUR_BOT_TOKEN

Author: Praveen Kothapally
License: MIT
"""

__version__ = "1.0.0"

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# ── Constants ─────────────────────────────────────────────────────────

SUPPORTED_AGENTS = {
    "hermes": {
        "config_dir": "~/.hermes",
        "name": "Hermes Agent",
        "critical_files": [
            "config.yaml",
            "auth.json",
            "SOUL.md",
            ".env",
            "channel_directory.json",
            "kanban.db",
            "gateway.db",
            "gateway_state.json",
        ],
        "critical_dirs": [
            "skills",
            "memories",
            "cron",
            "scripts",
            "hooks",
            "sessions",
            "logs",
            "checkpoints",
            "state-snapshots",
            "hermes-agent",
            "webui",
        ],
        "optional_dirs": [
            "cache",
            "image_cache",
            "audio_cache",
            "pastes",
            "pairing",
            "migration",
        ],
        "exclude_patterns": [
            "*.pyc",
            "__pycache__",
            "node_modules",
            ".git",
            ".DS_Store",
            "*.lock",
            "*.pid",
        ],
    },
    "claude-code": {
        "config_dir": "~/.claude",
        "name": "Claude Code",
        "critical_files": ["config.json", "settings.json"],
        "critical_dirs": ["projects", "history"],
        "optional_dirs": [],
        "exclude_patterns": ["*.pyc", "__pycache__", ".git", ".DS_Store"],
    },
    "codex": {
        "config_dir": "~/.codex",
        "name": "OpenAI Codex CLI",
        "critical_files": ["config.yaml", "settings.json"],
        "critical_dirs": ["projects", "history"],
        "optional_dirs": [],
        "exclude_patterns": ["*.pyc", "__pycache__"],
    },
    "opencode": {
        "config_dir": "~/.opencode",
        "name": "OpenCode CLI",
        "critical_files": ["config.yaml"],
        "critical_dirs": ["projects"],
        "optional_dirs": [],
        "exclude_patterns": ["*.pyc", "__pycache__"],
    },
    "auto": {
        "config_dir": "",
        "name": "Auto-detect",
        "critical_files": [],
        "critical_dirs": [],
        "optional_dirs": [],
        "exclude_patterns": [],
    },
}

BACKUP_CONFIG_FILE = "~/.agent-backup/config.yaml"

# ── Utility Functions ─────────────────────────────────────────────────


def expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


def load_config() -> Dict:
    config_path = expand(BACKUP_CONFIG_FILE)
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(config: Dict) -> None:
    config_path = expand(BACKUP_CONFIG_FILE)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def detect_agent() -> Optional[str]:
    home = Path.home()
    for agent_id, info in SUPPORTED_AGENTS.items():
        if agent_id == "auto":
            continue
        config_dir = expand(info["config_dir"])
        if config_dir.exists():
            return agent_id
    return None


def get_agent_info(agent_id: str) -> Dict:
    if agent_id == "auto":
        detected = detect_agent()
        if not detected:
            print("❌ No supported agent framework detected.")
            print("   Supported: " + ", ".join(k for k in SUPPORTED_AGENTS if k != "auto"))
            sys.exit(1)
        print(f"🔍 Auto-detected: {SUPPORTED_AGENTS[detected]['name']}")
        return {**SUPPORTED_AGENTS[detected], "id": detected}
    if agent_id not in SUPPORTED_AGENTS:
        print(f"❌ Unknown agent: {agent_id}")
        print("   Supported: " + ", ".join(k for k in SUPPORTED_AGENTS if k != "auto"))
        sys.exit(1)
    return {**SUPPORTED_AGENTS[agent_id], "id": agent_id}


def get_backup_items(agent_info: Dict, include_sessions: bool = True, include_logs: bool = False, include_optional: bool = False) -> tuple:
    config_dir = expand(agent_info["config_dir"])
    critical = []
    optional = []
    excluded = []

    for f in agent_info.get("critical_files", []):
        p = config_dir / f
        if p.exists():
            critical.append((p, False))
        else:
            print(f"   ⚠️  Missing critical file: {f}")

    for d in agent_info.get("critical_dirs", []):
        p = config_dir / d
        if p.exists():
            if include_sessions or d not in ("sessions", "webui"):
                critical.append((p, True))
            else:
                optional.append((p, True))
                print(f"   📦 Sessions excluded (--no-sessions set)")
        else:
            print(f"   ⚠️  Missing critical dir: {d}")

    if include_optional:
        for d in agent_info.get("optional_dirs", []):
            p = config_dir / d
            if p.exists():
                optional.append((p, True))

    if include_logs:
        log_dir = config_dir / "logs"
        if log_dir.exists():
            critical.append((log_dir, True))
    else:
        log_dir = config_dir / "logs"
        if log_dir.exists():
            excluded.append((log_dir, True))
            print(f"   📦 Logs excluded (--no-logs set)")

    return critical, optional, excluded


def humanize_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def calculate_size(paths: List[tuple]) -> int:
    total = 0
    for path, is_dir in paths:
        if is_dir:
            for root, dirs, files in os.walk(path):
                for f in files:
                    total += (Path(root) / f).stat().st_size
        else:
            total += path.stat().st_size
    return total


def should_exclude(path: Path, patterns: List[str]) -> bool:
    path_str = str(path)
    for pattern in patterns:
        if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(path.name, pattern):
            return True
        for part in path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def create_manifest(agent_id: str, agent_name: str, paths: List[tuple], output_path: Path) -> Dict:
    manifest = {
        "agent-backup": {
            "version": __version__,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "agent": {
                "id": agent_id,
                "name": agent_name,
                "hostname": os.uname().nodename if hasattr(os, "uname") else "unknown",
                "platform": sys.platform,
            },
            "backup": {
                "format": "tar.zst" if output_path.suffix == ".zst" else "tar.gz",
                "algorithm": "zstd-fast" if output_path.suffix == ".zst" else "gzip",
                "items_backed_up": len(paths),
                "paths": [str(p.relative_to(expand("~"))) for p, _ in paths],
            },
            "restore_instructions": {
                "method": "agent-backup restore",
                "example": f"agent-backup restore --from {output_path.name} --to ~/.{agent_id}",
            },
        }
    }
    return manifest


def check_compression_tool(fmt: str) -> Optional[str]:
    tools = {
        "zst": ["zstd", "zstdmt"],
        "gz": ["gzip", "pigz"],
    }
    if fmt not in tools:
        return "tar"
    for tool in tools[fmt]:
        if subprocess.run(["which", tool], capture_output=True).returncode == 0:
            return tool
    return None


def create_backup(agent_info: Dict, output_path: Path, compression: str = "auto", dry_run: bool = False) -> Path:
    config_dir = expand(agent_info["config_dir"])
    agent_id = agent_info["id"]

    print(f"📦 Creating backup of {agent_info['name']}")
    print(f"   Source: {config_dir}")
    print(f"   Target: {output_path}")

    if compression == "auto":
        if check_compression_tool("zst"):
            compression = "zst"
        else:
            compression = "gz"
        print(f"   Compression: {compression} (auto-selected)")
    else:
        print(f"   Compression: {compression}")

    critical, optional, excluded = get_backup_items(agent_info)
    all_items = critical + optional

    if not all_items:
        print("❌ No items found to backup")
        sys.exit(1)

    total_size = calculate_size(all_items)
    print(f"   Items: {len(all_items)} ({humanize_size(total_size)})")

    if dry_run:
        print("\n🧪 DRY RUN — Would backup:")
        for path, is_dir in all_items:
            print(f"   {'📁' if is_dir else '📄'} {path}")
        print(f"\n   Output: {output_path}")
        return output_path

    if compression == "zst":
        output_path = output_path.with_suffix(".tar.zst")
        tar_path = output_path.with_suffix("")
    elif compression in ("gz", "bz2", "xz"):
        output_path = output_path.with_suffix(f".tar.{compression}")
        tar_path = output_path.with_suffix("")
    else:
        output_path = output_path.with_suffix(".tar")
        tar_path = output_path
        compression = None

    print(f"   Archive: {output_path.name}")

    with tarfile.open(str(tar_path), "w") as tar:
        for path, is_dir in all_items:
            if not path.exists():
                continue
            arcname = path.relative_to(Path.home())
            print(f"   Adding {'📁' if is_dir else '📄'} {arcname}")
            tar.add(path, arcname=str(arcname))

    if compression == "zst":
        tool = check_compression_tool("zst")
        if tool:
            subprocess.run([tool, "-f", "--rm", str(tar_path), "-o", str(output_path)], check=True)
        else:
            subprocess.run(["gzip", "-f", str(tar_path)], check=True)
            output_path = tar_path.with_suffix(".gz")
    elif compression == "gz":
        subprocess.run(["gzip", "-f", str(tar_path)], check=True)
    elif compression in ("bz2", "xz"):
        mode = "-cJf" if compression == "xz" else "-cjf"
        subprocess.run(["tar", mode, str(output_path), "-C", str(tar_path.parent), tar_path.name], check=True)
        tar_path.unlink(missing_ok=True)

    manifest = create_manifest(agent_id, agent_info["name"], all_items, output_path)
    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    actual_size = output_path.stat().st_size
    ratio = (total_size / actual_size) if actual_size > 0 else 0
    print(f"\n✅ Backup complete!")
    print(f"   Archive: {output_path}")
    print(f"   Size: {humanize_size(actual_size)} (compression: {ratio:.1f}x)")
    print(f"   Manifest: {manifest_path}")

    return output_path


def restore_backup(archive_path: Path, target_dir: Path, verify: bool = True, dry_run: bool = False) -> None:
    print(f"📥 Restoring from {archive_path}")
    print(f"   Target: {target_dir}")

    if not archive_path.exists():
        print(f"❌ Archive not found: {archive_path}")
        sys.exit(1)

    suffix = ".".join(archive_path.suffixes)
    if ".zst" in suffix:
        compression = "zst"
    elif ".gz" in suffix or ".tgz" in suffix:
        compression = "gz"
    elif ".bz2" in suffix:
        compression = "bz2"
    elif ".xz" in suffix:
        compression = "xz"
    else:
        compression = None

    if dry_run:
        print("\n🧪 DRY RUN — Would restore to:")
        print(f"   {target_dir}")
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    if compression == "zst":
        tool = check_compression_tool("zst")
        tar_path = tempfile.NamedTemporaryFile(suffix=".tar", delete=False)
        tar_path.close()
        if tool:
            subprocess.run([tool, "-d", "-f", str(archive_path), "-o", tar_path.name], check=True)
        else:
            print("❌ zstd not available for decompression")
            sys.exit(1)
        with tarfile.open(tar_path.name, "r:") as tar:
            tar.extractall(target_dir)
        os.unlink(tar_path.name)
    elif compression == "gz":
        with tarfile.open(str(archive_path), "r:gz") as tar:
            tar.extractall(target_dir)
    elif compression == "bz2":
        with tarfile.open(str(archive_path), "r:bz2") as tar:
            tar.extractall(target_dir)
    elif compression == "xz":
        with tarfile.open(str(archive_path), "r:xz") as tar:
            tar.extractall(target_dir)
    else:
        with tarfile.open(str(archive_path), "r:") as tar:
            tar.extractall(target_dir)

    manifest_path = archive_path.with_suffix(archive_path.suffix + ".manifest.json")
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        print(f"\n📋 Manifest verification:")
        print(f"   Agent: {manifest['agent-backup']['agent']['name']}")
        print(f"   Backup version: {manifest['agent-backup']['version']}")
        print(f"   Created: {manifest['agent-backup']['created_at']}")

    print(f"\n✅ Restore complete!")
    print(f"   Restored to: {target_dir}")
    print(f"\n💡 Next steps:")
    print(f"   1. Verify the restored files")
    print(f'   2. Run: export AGENT_HOME="{target_dir}"')
    print(f"   3. Restart your agent framework")


def setup_schedule(agent_id: str, frequency: str, time_str: str, output_dir: Path) -> None:
    print(f"📅 Setting up {frequency} backups for {agent_id}")

    if frequency == "hourly":
        cron = "0 * * * *"
        desc = "Every hour"
    elif frequency == "daily":
        cron = f"{time_str.split(':')[1]} {time_str.split(':')[0]} * * *"
        desc = f"Daily at {time_str}"
    elif frequency == "weekly":
        cron = f"{time_str.split(':')[1]} {time_str.split(':')[0]} * * 0"
        desc = f"Weekly on Sunday at {time_str}"
    elif frequency == "monthly":
        cron = f"{time_str.split(':')[1]} {time_str.split(':')[0]} 1 * *"
        desc = f"Monthly on 1st at {time_str}"
    elif frequency == "custom":
        print("Enter custom cron expression (e.g., '0 */6 * * *' for every 6 hours):")
        cron = input("> ")
        desc = f"Custom: {cron}"
    else:
        print(f"❌ Unknown frequency: {frequency}")
        return

    backup_cmd = f"agent-backup backup --agent {agent_id} --to {output_dir} --quiet"
    cron_job = f"{cron} {backup_cmd} >> ~/.agent-backup/backup.log 2>>> ~/.agent-backup/backup.log"

    config = load_config()
    if "schedules" not in config:
        config["schedules"] = []
    config["schedules"].append({
        "agent": agent_id,
        "frequency": frequency,
        "cron": cron,
        "time": time_str,
        "output_dir": str(output_dir),
        "enabled": True,
    })
    save_config(config)

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
        lines = existing.split("\n")
        new_lines = [l for l in lines if f"--agent {agent_id}" not in l and l.strip()]
        new_lines.append(f"# Agent Backup: {agent_id} ({desc})")
        new_lines.append(cron_job)
        new_lines.append("")
        cron_input = "\n".join(new_lines)
        subprocess.run(["crontab", "-"], input=cron_input, text=True, check=True)
        print(f"✅ Schedule set: {desc}")
        print(f"   Command: {backup_cmd}")
        print(f"   Output: {output_dir}")
        print(f"   Cron: {cron}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install cron job: {e}")
        print("   Add this cron job manually:")
        print(f"   {cron_job}")


def remove_schedule(agent_id: str) -> None:
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            print("No crontab found.")
            return
        lines = result.stdout.split("\n")
        new_lines = [l for l in lines if f"--agent {agent_id}" not in l]
        new_lines = [l for l in new_lines if f"Agent Backup: {agent_id}" not in l]
        if len(new_lines) == len(lines):
            print(f"ℹ️  No schedule found for {agent_id}")
            return
        subprocess.run(["crontab", "-"], input="\n".join(new_lines), text=True, check=True)
        config = load_config()
        if "schedules" in config:
            config["schedules"] = [s for s in config["schedules"] if s["agent"] != agent_id]
            save_config(config)
        print(f"✅ Removed schedule for {agent_id}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to remove schedule: {e}")


def list_schedules() -> None:
    config = load_config()
    schedules = config.get("schedules", [])
    if not schedules:
        print("No schedules configured.")
        return
    print("📅 Backup Schedules:")
    print("-" * 60)
    for s in schedules:
        status = "✅" if s.get("enabled", True) else "⏸️"
        print(f"   {status} {s['agent']}: {s['frequency']} at {s['time']}")
        print(f"      → {s['output_dir']}")


def list_backups(backup_dir: Path) -> None:
    if not backup_dir.exists():
        print(f"❌ Backup directory not found: {backup_dir}")
        return
    backups = sorted(backup_dir.glob("*.tar.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print(f"No backups found in {backup_dir}")
        return
    print(f"📁 Backups in {backup_dir}:")
    print("-" * 80)
    print(f"{'Date':<20} {'Agent':<15} {'Size':<12} {'File'}")
    print("-" * 80)
    for b in backups:
        mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size = humanize_size(b.stat().st_size)
        name_parts = b.name.replace(".tar.zst", "").replace(".tar.gz", "").split("-")
        agent = name_parts[0] if len(name_parts) > 0 else "unknown"
        print(f"{mtime:<20} {agent:<15} {size:<12} {b.name}")
    print(f"\nTotal: {len(backups)} backups")


def setup_telegram_bot(token: str) -> None:
    config = load_config()
    if "telegram" not in config:
        config["telegram"] = {}
    config["telegram"]["bot_token"] = token
    config["telegram"]["enabled"] = True
    save_config(config)
    print("✅ Telegram bot configured!")
    print("   Send /backup to your bot to trigger a backup remotely")
    print("   Send /restore to get the latest backup file")
    print("   Send /status to check agent status")


def main():
    parser = argparse.ArgumentParser(
        description="Agent Backup — Universal AI Agent Backup & Restore Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s backup --agent hermes --to ~/backups
  %(prog)s restore --from ~/backups/hermes-20260503.tar.zst --to ~/.hermes
  %(prog)s schedule --agent hermes --frequency daily --time 02:00 --to ~/backups
  %(prog)s telegram-bot --token 123456:ABC-DEF1234ghIkl
""",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    backup_parser = subparsers.add_parser("backup", help="Create a backup")
    backup_parser.add_argument("--agent", default="auto", choices=list(SUPPORTED_AGENTS.keys()))
    backup_parser.add_argument("--to", required=True)
    backup_parser.add_argument("--compression", default="auto", choices=["auto", "zst", "gz", "bz2", "xz", "none"])
    backup_parser.add_argument("--no-sessions", action="store_true")
    backup_parser.add_argument("--no-logs", action="store_true")
    backup_parser.add_argument("--exclude", action="append", default=[])
    backup_parser.add_argument("--quiet", action="store_true")
    backup_parser.add_argument("--dry-run", action="store_true")

    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("--from", dest="source", required=True)
    restore_parser.add_argument("--to", default="~/.hermes")
    restore_parser.add_argument("--verify", action="store_true", default=True)
    restore_parser.add_argument("--dry-run", action="store_true")

    list_parser = subparsers.add_parser("list", help="List backups")
    list_parser.add_argument("--from", dest="source_dir", required=True)

    schedule_parser = subparsers.add_parser("schedule", help="Setup automatic backups")
    schedule_parser.add_argument("--agent", default="auto", choices=list(SUPPORTED_AGENTS.keys()))
    schedule_parser.add_argument("--frequency", default="daily", choices=["hourly", "daily", "weekly", "monthly", "custom"])
    schedule_parser.add_argument("--time", default="02:00")
    schedule_parser.add_argument("--to", required=True)

    unschedule_parser = subparsers.add_parser("unschedule", help="Remove schedule")
    unschedule_parser.add_argument("--agent", required=True)

    subparsers.add_parser("schedules", help="List schedules")

    telegram_parser = subparsers.add_parser("telegram-bot", help="Configure Telegram bot")
    telegram_parser.add_argument("--token", required=True)

    status_parser = subparsers.add_parser("status", help="Check agent status")
    status_parser.add_argument("--agent", default="auto", choices=list(SUPPORTED_AGENTS.keys()))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "backup":
        agent_info = get_agent_info(args.agent)
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = expand(args.to)
        output_dir.mkdir(parents=True, exist_ok=True)
        hostname = os.uname().nodename if hasattr(os, "uname") else "local"
        filename = f"{agent_info['id']}-{hostname}-{now}"
        output_path = output_dir / filename
        create_backup(agent_info, output_path, args.compression, dry_run=args.dry_run)

    elif args.command == "restore":
        source = expand(args.source)
        target = expand(args.to)
        restore_backup(source, target, verify=args.verify, dry_run=args.dry_run)

    elif args.command == "list":
        list_backups(expand(args.source_dir))

    elif args.command == "schedule":
        agent_info = get_agent_info(args.agent)
        setup_schedule(agent_info["id"], args.frequency, args.time, expand(args.to))

    elif args.command == "unschedule":
        remove_schedule(args.agent)

    elif args.command == "schedules":
        list_schedules()

    elif args.command == "telegram-bot":
        setup_telegram_bot(args.token)

    elif args.command == "status":
        agent_info = get_agent_info(args.agent)
        config_dir = expand(agent_info["config_dir"])
        print(f"📊 {agent_info['name']}")
        print(f"   Config dir: {config_dir}")
        print(f"   Exists: {'✅' if config_dir.exists() else '❌'}")
        if config_dir.exists():
            size = sum(f.stat().st_size for f in config_dir.rglob("*") if f.is_file())
            print(f"   Size: {humanize_size(size)}")
        config = load_config()
        last_backup = config.get("last_backups", {}).get(agent_info["id"])
        if last_backup:
            print(f"   Last backup: {last_backup}")
        else:
            print(f"   Last backup: Never")


def telegram_bot_main():
    config = load_config()
    telegram_cfg = config.get("telegram", {})
    token = telegram_cfg.get("bot_token")
    if not token:
        print("❌ Telegram bot not configured. Run: agent-backup telegram-bot --token YOUR_TOKEN")
        sys.exit(1)
    try:
        from telegram import Update
        from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
    except ImportError:
        print("❌ python-telegram-bot not installed. Run: pip install 'python-telegram-bot>=21.0'")
        sys.exit(1)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"🤖 Agent Backup Bot v{__version__}\n\n"
            "Commands:\n"
            "/backup — Trigger a backup now\n"
            "/restore — Get latest backup file\n"
            "/list — List recent backups\n"
            "/status — Check agent status\n"
            "/help — Show all commands"
        )

    async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("⏳ Starting backup...")
        agent_id = detect_agent()
        if not agent_id:
            await update.message.reply_text("❌ No agent detected")
            return
        agent_info = get_agent_info(agent_id)
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = expand("~/.agent-backup/archives")
        backup_dir.mkdir(parents=True, exist_ok=True)
        output_path = backup_dir / f"{agent_id}-telegram-{now}"
        try:
            path = create_backup(agent_info, output_path, dry_run=False)
            await update.message.reply_document(document=open(str(path), "rb"), caption=f"✅ Backup: {path.name}")
            manifest_path = path.with_suffix(path.suffix + ".manifest.json")
            if manifest_path.exists():
                await update.message.reply_document(document=open(str(manifest_path), "rb"), caption="📋 Manifest")
        except Exception as e:
            await update.message.reply_text(f"❌ Backup failed: {e}")

    async def restore_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        backup_dir = expand("~/.agent-backup/archives")
        if not backup_dir.exists():
            await update.message.reply_text("❌ No backups found")
            return
        backups = sorted(backup_dir.glob("*.tar.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not backups:
            await update.message.reply_text("❌ No backups found")
            return
        latest = backups[0]
        await update.message.reply_text(
            f"📥 Latest: {latest.name}\n"
            f"Size: {humanize_size(latest.stat().st_size)}\n\n"
            f"Download and restore:\n"
            f"```agent-backup restore --from {latest} --to ~/.{detect_agent()}```",
            parse_mode="Markdown",
        )

    async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        backup_dir = expand("~/.agent-backup/archives")
        if not backup_dir.exists():
            await update.message.reply_text("❌ No backups found")
            return
        backups = sorted(backup_dir.glob("*.tar.*"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        msg = "📁 Recent Backups:\n\n"
        for i, b in enumerate(backups, 1):
            date = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size = humanize_size(b.stat().st_size)
            msg += f"{i}. `{b.name}`\n   {date} | {size}\n\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        agent_id = detect_agent()
        if not agent_id:
            await update.message.reply_text("❌ No agent detected")
            return
        agent_info = get_agent_info(agent_id)
        config_dir = expand(agent_info["config_dir"])
        status_text = f"📊 {agent_info['name']}\n"
        status_text += f"Config: {config_dir}\n"
        if config_dir.exists():
            size = sum(f.stat().st_size for f in config_dir.rglob("*") if f.is_file())
            status_text += f"Size: {humanize_size(size)}\n"
            status_text += f"Status: ✅ Active"
        else:
            status_text += f"Status: ❌ Not found"
        await update.message.reply_text(status_text)

    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await start(update, context)

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("restore", restore_cmd))
    app.add_handler(CommandHandler("list", list_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    print(f"🤖 Agent Backup Bot started")
    print(f"   Send /start to your Telegram bot to begin")
    app.run_polling()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "telegram-bot-run":
        telegram_bot_main()
    else:
        main()
