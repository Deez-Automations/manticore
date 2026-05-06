#!/bin/bash
# ============================================================
# MANTICORE — Start Services
# Run this every time you spin up the droplet after setup
# ============================================================
set -euo pipefail

echo "=== [1/5] Start vLLM inside rocm container ==="
# vLLM lives inside the pre-installed 'rocm' Docker container
# Check if already running
if docker exec rocm bash -c "ps aux | grep 'vllm serve' | grep -v grep" &>/dev/null; then
  echo "vLLM already running — skipping"
else
  docker exec -d rocm bash -c "
    VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 vllm serve Qwen/Qwen2.5-72B-Instruct \
      --host 0.0.0.0 \
      --port 8000 \
      --max-model-len 65536 \
      --enable-auto-tool-choice \
      --tool-call-parser hermes \
      &> /tmp/vllm.log
  "
  echo "vLLM starting... waiting 90s for model to load"
  sleep 90
fi

echo "=== [2/5] Verify vLLM is responding ==="
curl -s http://localhost:8000/v1/models | python3 -m json.tool | grep '"id"'
echo "vLLM OK"

echo "=== [3/5] Start DVWA ==="
if docker ps | grep dvwa &>/dev/null; then
  echo "DVWA already running"
elif docker ps -a | grep dvwa &>/dev/null; then
  docker start dvwa
  echo "DVWA restarted"
else
  docker run -d --name dvwa -p 8080:80 vulnerables/web-dvwa
  echo "DVWA started — go to http://<droplet-ip>:8080, login admin/password, click 'Create/Reset Database'"
  # Open firewall
  ufw allow 8080 2>/dev/null || true
fi

echo "=== [4/5] Set up DVWA source for Shannon ==="
if [ -d /root/dvwa-src/.git ]; then
  echo "DVWA source already initialized"
else
  # Wait for DVWA to be up
  sleep 5
  DVWA_CONTAINER=$(docker ps | grep dvwa | awk '{print $1}' | head -1)
  docker cp "$DVWA_CONTAINER":/var/www/html /root/dvwa-src
  cd /root/dvwa-src
  git init
  git add -A
  git commit -m "dvwa source"
  echo "DVWA source ready at /root/dvwa-src"
fi

echo "=== [5/5] Start Temporal ==="
cd /root/manticore
docker compose ps | grep -q "healthy" && echo "Temporal already running" || docker compose up -d

echo ""
echo "=== All services up! ==="
echo ""
echo "Run scan:"
echo "  cd /root/manticore"
echo "  ./manticore start -u http://host.docker.internal:8080 -r /root/dvwa-src -w dvwa-scan"
echo ""
echo "Watch logs:"
echo "  ./manticore logs dvwa-scan"
