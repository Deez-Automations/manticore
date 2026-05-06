#!/bin/bash
# ============================================================
# MANTICORE — Fresh Droplet Setup Script
# Run this ONCE on a brand new AMD MI300X vLLM 1-Click droplet
# DigitalOcean image: vLLM 0.17.1 on Ubuntu 24.04 + ROCm
# ============================================================
set -euo pipefail

echo "=== [1/8] Configure git identity ==="
git config --global user.email "daniyal.itservices@gmail.com"
git config --global user.name "Muhammad Daniyal"
git config --global init.defaultBranch main

echo "=== [2/8] Install Node.js 22 ==="
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

echo "=== [3/8] Install pnpm ==="
npm install -g pnpm

echo "=== [4/8] Clone Manticore repo ==="
cd /root
git clone https://github.com/Deez-Automations/manticore
cd /root/manticore

echo "=== [5/8] Install JS deps and build TypeScript ==="
pnpm install
pnpm build

echo "=== [6/8] Fix root-user check in compiled CLI ==="
# Shannon blocks root users — patch the compiled output
sed -i 's/const isRoot = process\.geteuid?.()/const isRoot = false\/\/ ()/g' apps/cli/dist/index.mjs || \
sed -i 's/const isRoot=process\.geteuid?.()/const isRoot=false\/\/()/g' apps/cli/dist/index.mjs || \
# Fallback: grep for the exact line and patch it
LINE=$(grep -n "isRoot" apps/cli/dist/index.mjs | grep "geteuid" | cut -d: -f1 | head -1)
if [ -n "$LINE" ]; then
  sed -i "${LINE}s/.*/const isRoot = false;/" apps/cli/dist/index.mjs
  echo "Patched isRoot at line $LINE"
else
  echo "WARNING: Could not find isRoot line — check apps/cli/dist/index.mjs manually"
fi

echo "=== [7/8] Write .env ==="
cat > /root/manticore/.env << 'EOF'
ANTHROPIC_BASE_URL=http://host.docker.internal:8000/v1
ANTHROPIC_AUTH_TOKEN=placeholder
ANTHROPIC_SMALL_MODEL=Qwen/Qwen2.5-72B-Instruct
ANTHROPIC_MEDIUM_MODEL=Qwen/Qwen2.5-72B-Instruct
ANTHROPIC_LARGE_MODEL=Qwen/Qwen2.5-72B-Instruct
CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000
EOF

echo "=== [8/8] Build Manticore Docker image ==="
./manticore build

echo ""
echo "=== Setup complete! ==="
echo "Next: run ./scripts/start-services.sh"
