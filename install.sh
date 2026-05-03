#!/bin/bash
# install-agent-backup.sh — One-command installer for Agent Backup
set -e

echo "🚀 Installing Agent Backup..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check pip
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo "❌ pip is required but not installed"
    exit 1
fi

# Check zstd
if ! command -v zstd &> /dev/null; then
    echo "⚠️  zstd not found. Installing..."
    if command -v brew &> /dev/null; then
        brew install zstd
    elif command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y zstd
    else
        echo "   Please install zstd manually (fallback to gzip available)"
    fi
fi

# Clone or install
if [ -d ".git" ] && [ -f "pyproject.toml" ]; then
    pip install -e "."
else
    pip install agent-backup
fi

echo ""
echo "✅ Agent Backup installed!"
echo ""
echo "Quick start:"
echo "  agent-backup status --agent hermes"
echo "  agent-backup backup --agent hermes --to ~/backups"
echo ""
echo "Setup Telegram bot:"
echo "  agent-backup telegram-bot --token YOUR_BOT_TOKEN"
echo ""
echo "Setup scheduling:"
echo "  agent-backup schedule --agent hermes --frequency daily --time 02:00 --to ~/backups"
