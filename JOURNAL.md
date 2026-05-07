# Manticore — Hackathon War Room Journal
**Last Updated:** 2026-05-07
**Deadline:** May 8, 2026 — TOMORROW
**Prize Pool:** $21,500+
**Repo:** https://github.com/Deez-Automations/manticore

---

## READ THIS FIRST — For the AI Joining Session 4

You are joining at the last quarter. The droplet is destroyed. A new one needs to be spun up. There is exactly one unconfirmed blocker left. Everything else is solved and committed to GitHub. Your job is to get the pipeline running end-to-end and then ship the submission. Read this entire document before touching anything.

---

## What We're Building

**Manticore** — autonomous AI pentesting agent. Takes a target URL, runs recon, finds real vulnerabilities in the source code, attempts exploits, and generates a professional security report.

**The AMD angle:** Enterprise security teams cannot send customer network traffic to OpenAI. Local inference on AMD MI300X IS the product, not just a feature. This is the core pitch.

**Track:** AI Agents & Agentic Workflows (Track 1)
**Base:** Forked from Shannon (open source AI pentester by Keygraph). Rebranded surface-level. AGPL v3 license kept, Shannon credited at bottom of README only.

---

## Architecture — How It All Fits Together

```
[DVWA running on port 8080]          ← demo target (vulnerable PHP app)
        ↓
[./manticore start -u ... -r ...]    ← CLI kicks off everything
        ↓
[Temporal workflow engine]           ← orchestrates 13 agents
        ↓
[Shannon worker Docker container]    ← runs agents, mounts DVWA source code
        ↓
[claude-code binary inside worker]   ← the actual agent runtime
        ↓
[vLLM inside 'rocm' container]       ← Qwen2.5-72B-Instruct on AMD MI300X
        ↓
[manticore_engine/run.py]            ← Phase 6: chain synthesis on findings
        ↓
[HackerOne-style report]             ← deliverable
```

### The 5-Phase Pipeline (Shannon)
1. **pre-recon** — reads DVWA source code, builds architectural baseline (LARGE model)
2. **recon** — maps attack surface from pre-recon findings (MEDIUM model)
3. **vuln analysis** — 5 parallel agents: injection, xss, auth, authz, ssrf (MEDIUM model)
4. **exploitation** — 5 parallel agents, conditional on vuln findings (MEDIUM model)
5. **report** — executive security report (MEDIUM model)

### Phase 6 (Our Addition — manticore_engine/)
After Shannon completes, run:
```bash
python manticore_engine/run.py ./workspaces/dvwa-scan/deliverables http://host.docker.internal:8080
```
Three Qwen agents (Queen pattern):
- **Chain Builder** — reads all findings JSONs, proposes multi-step attack chains
- **Validator** — rejects chains with missing steps or ungrounded assumptions
- **Executor** — converts approved chains to exact Playwright steps + CVSS 3.1 scoring

Output: severity upgrade card showing BEFORE (3x Medium) → AFTER (CHIMERA-001 CRITICAL 9.8)

---

## Infrastructure — The Droplet

**Provider:** AMD Developer Cloud via DigitalOcean
**Image:** DigitalOcean vLLM 1-Click (Ubuntu 24.04 + ROCm + vLLM 0.17.1)
**GPU:** MI300X, 1 GPU, $1.99/hr — **DESTROY when not working, billed even when off**
**Credits:** $100, expires June 4, 2026

### Critical: vLLM is INSIDE Docker, not on the host
The 1-Click image runs vLLM inside a container named `rocm`. Everything about vLLM happens there.
```bash
docker exec -it rocm /bin/bash        # enter vLLM container
docker exec rocm bash -c "tail -f /tmp/vllm.log"   # check logs without entering
```

### Starting vLLM (run from HOST, not inside rocm)
```bash
docker exec -d rocm bash -c "VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 vllm serve Qwen/Qwen2.5-72B-Instruct --host 0.0.0.0 --port 8000 --max-model-len 65536 --enable-auto-tool-choice --tool-call-parser hermes &> /tmp/vllm.log"
```
- `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1` — required, model config normally caps at 32768
- `--enable-auto-tool-choice --tool-call-parser hermes` — required for tool use via Messages API
- Wait ~90 seconds for model to fully load before testing

### Verify vLLM is ready
```bash
curl -s http://localhost:8000/v1/models | python3 -m json.tool
# Should return: "id": "Qwen/Qwen2.5-72B-Instruct"
```

---

## Session 4 — First Thing To Do

### Step 1: Spin up new MI300X droplet
DigitalOcean → GPU Droplets → vLLM 1-Click → MI300X 1 GPU → Ubuntu 24.04 → SSH key → Create

### Step 2: Run setup script
```bash
git clone https://github.com/Deez-Automations/manticore /root/manticore
cd /root/manticore
chmod +x scripts/*.sh
./scripts/droplet-setup.sh
```
This installs Node 22, pnpm, builds TypeScript, patches the root check, writes .env, builds Docker image. ~15 minutes.

### Step 3: Start all services
```bash
./scripts/start-services.sh
```
Starts vLLM, DVWA, Temporal, initializes DVWA source git repo.

### Step 4: THE CRITICAL TEST — do this before running the scanner
```bash
curl -s http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-api-key: placeholder" \
  -d '{"model": "Qwen/Qwen2.5-72B-Instruct", "max_tokens": 50, "messages": [{"role": "user", "content": "say hi"}]}' \
  --max-time 60
```

**If this returns a response within 60 seconds → everything works, proceed to Step 5.**

**If this hangs → use LiteLLM proxy (see Fallback section below). Do not waste time debugging vLLM internals.**

### Step 5: Run the scanner
```bash
cd /root/manticore
./manticore start -u http://host.docker.internal:8080 -r /root/dvwa-src -w dvwa-scan
./manticore logs dvwa-scan
```

### Step 6: After scan completes, run chain synthesis
```bash
cd /root/manticore
pip install openai
python manticore_engine/run.py ./workspaces/dvwa-scan/deliverables http://host.docker.internal:8080
```

---

## The One Unconfirmed Blocker

Shannon's pre-recon agent fails in ~400ms: `Invalid request: There's an issue with the selected model (Qwen/Qwen2.5-72B-Instruct)`

**What we know for certain:**
- vLLM runs and Qwen model is loaded (confirmed via `/v1/models`)
- All Shannon config bugs are fixed (see fixes below)
- The error is real — not a config issue we missed

**Most likely cause:**
During session 3, we ran many failed scans. Each failure left zombie requests queued in vLLM. By the end, vLLM's queue was saturated — `/v1/messages` hung because the GPU was processing stale garbage from previous runs. On a fresh droplet with no history, this should not happen.

**If it still fails on fresh droplet:**
The claude-code binary (v2.1.84 installed inside the Shannon Docker image) may not be fully compatible with vLLM's Messages API format. Use LiteLLM proxy — 30 minute fix.

---

## LiteLLM Fallback Plan

If the Messages API test hangs, run LiteLLM as a proxy between claude-code and vLLM:

```bash
pip install litellm
```

Create `/root/litellm-config.yaml`:
```yaml
model_list:
  - model_name: Qwen/Qwen2.5-72B-Instruct
    litellm_params:
      model: openai/Qwen/Qwen2.5-72B-Instruct
      api_base: http://localhost:8000/v1
      api_key: placeholder
```

Run proxy:
```bash
litellm --config /root/litellm-config.yaml --port 9000 &
```

Update `/root/manticore/.env`:
```
ANTHROPIC_BASE_URL=http://host.docker.internal:9000/v1
ANTHROPIC_AUTH_TOKEN=placeholder
ANTHROPIC_SMALL_MODEL=Qwen/Qwen2.5-72B-Instruct
ANTHROPIC_MEDIUM_MODEL=Qwen/Qwen2.5-72B-Instruct
ANTHROPIC_LARGE_MODEL=Qwen/Qwen2.5-72B-Instruct
CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000
```

LiteLLM translates Anthropic Messages format → OpenAI chat/completions → vLLM. This is a known working pattern.

---

## All Fixes Applied (Already in GitHub)

Everything below is already committed. Do not redo these. Just clone and run setup script.

### 1. Root user check (`apps/cli/dist/index.mjs`)
Shannon blocks root users. The `droplet-setup.sh` script patches this automatically:
```bash
LINE=$(grep -n "isRoot" apps/cli/dist/index.mjs | grep "geteuid" | cut -d: -f1 | head -1)
sed -i "${LINE}s/.*/const isRoot = false;/" apps/cli/dist/index.mjs
```

### 2. Entrypoint crash (`entrypoint.sh`)
When running as root (UID=0), entrypoint tried `groupadd -g 0 pentest` which fails because GID 0 is already `root`. `set -e` killed the container. Only log output was `groupadd: GID '0' already exists`.
Fix: skip UID remapping entirely when `TARGET_UID=0`. Already in repo.

### 3. Preflight validation (`apps/worker/src/services/preflight.ts`)
Shannon validates credentials by making a live SDK query before agents run. vLLM rejects this because it uses `claude-haiku-4-5-20251001` (default small model) which doesn't exist in vLLM.
Fix: early return when custom base URL is configured. Already in repo.

### 4. Multiple providers error
Shannon CLI rejects if both `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are set simultaneously.
Fix: use ONLY `ANTHROPIC_AUTH_TOKEN` in `.env`. Never set `ANTHROPIC_API_KEY`. If shell has old exports, clear them:
```bash
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL
```

### 5. ANTHROPIC_SMALL_MODEL missing
Even with preflight bypassed, the claude-code binary makes its own validation call using the small model tier. Default is `claude-haiku-4-5-20251001` — vLLM 404s on it.
Fix: set `ANTHROPIC_SMALL_MODEL=Qwen/Qwen2.5-72B-Instruct` in `.env`. Already in setup script.

### 6. ANTHROPIC_BASE_URL networking
Must use `host.docker.internal`, NOT `localhost` or the rocm container IP.
Worker runs inside `shannon-net` Docker network. `host.docker.internal` resolves to the host, which forwards to vLLM on port 8000.
Wrong: `http://172.17.0.2:8000/v1`
Wrong: `http://localhost:8000/v1`
Correct: `http://host.docker.internal:8000/v1`

### 7. DVWA source needs git init
Shannon requires the repo to have a `.git` directory. DVWA source is copied from container — no git by default.
Fix: already handled in `start-services.sh`:
```bash
docker cp dvwa:/var/www/html /root/dvwa-src
cd /root/dvwa-src && git init && git add -A && git commit -m "dvwa source"
```

### 8. CLAUDE_CODE_MAX_OUTPUT_TOKENS
vLLM's max_model_len is 65536. Shannon defaults to 64000 output tokens which exceeds it.
Fix: set `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000` in `.env`.

---

## .env — Final Confirmed Version

```
ANTHROPIC_BASE_URL=http://host.docker.internal:8000/v1
ANTHROPIC_AUTH_TOKEN=placeholder
ANTHROPIC_SMALL_MODEL=Qwen/Qwen2.5-72B-Instruct
ANTHROPIC_MEDIUM_MODEL=Qwen/Qwen2.5-72B-Instruct
ANTHROPIC_LARGE_MODEL=Qwen/Qwen2.5-72B-Instruct
CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000
```

---

## Submission Checklist — What's Left

### Must ship by May 8
- [ ] Shannon pipeline produces findings JSONs against DVWA
- [ ] `manticore_engine/run.py` produces chain synthesis output
- [ ] Demo video — 3 minutes max, show the agent running live
- [ ] Slide deck — one page minimum, required for submission
- [ ] Hugging Face Space — join AMD hackathon HF org, publish space
- [ ] lablab.ai form — title, description, tags, cover image, GitHub URL, HF Space URL, video link

### Social (bonus prizes — do alongside build)
- [ ] Social post when first successful chain is produced — tag @lablab @AIatAMD on X, AMD Developer on LinkedIn
- [ ] ROCm feedback post — document setup friction (required for AMD R9700 GPU prize)

### Bonus prizes in range
- Qwen partner prize: using Qwen2.5-72B ✓
- AMD R9700 GPU: best build-in-public social story
- HF Space likes prize: community engagement

---

## Repo Structure

```
manticore                   ← CLI entry point (Node.js)
manticore_engine/
  synthesize.py             ← reads findings, calls Qwen, outputs attack chains JSON
  report.py                 ← HackerOne-style markdown report
  agents.py                 ← Queen pattern: Chain Builder, Validator, Executor
  run.py                    ← single entry point (synthesis + report)
  requirements.txt          ← openai>=1.0.0
scripts/
  droplet-setup.sh          ← one-shot fresh droplet setup
  start-services.sh         ← start vLLM + DVWA + Temporal every session
  debug-notes.md            ← every gotcha documented
apps/cli/                   ← Shannon CLI (do not modify)
apps/worker/                ← Shannon pipeline (only modified preflight.ts)
entrypoint.sh               ← Docker entrypoint (patched for root user)
Dockerfile                  ← builds shannon-worker image
docker-compose.yml          ← Temporal infra only
```

---

## Key Commands Reference

```bash
# SSH
ssh root@<new-droplet-ip>

# First time setup
git clone https://github.com/Deez-Automations/manticore /root/manticore
cd /root/manticore && ./scripts/droplet-setup.sh

# Every session
./scripts/start-services.sh

# Test vLLM Messages API (do this before running scanner)
curl -s http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-api-key: placeholder" \
  -d '{"model": "Qwen/Qwen2.5-72B-Instruct", "max_tokens": 50, "messages": [{"role": "user", "content": "say hi"}]}' \
  --max-time 60

# Run scanner
./manticore start -u http://host.docker.internal:8080 -r /root/dvwa-src -w dvwa-scan
./manticore logs dvwa-scan

# Watch vLLM logs
docker exec rocm bash -c "tail -f /tmp/vllm.log"

# Run chain synthesis (after scanner completes)
python manticore_engine/run.py ./workspaces/dvwa-scan/deliverables http://host.docker.internal:8080

# Check workspace output
ls workspaces/dvwa-scan/
```
