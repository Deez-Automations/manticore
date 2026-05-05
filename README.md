<div align="center">
  <img src="./assets/banner.png" alt="Manticore" width="100%">
</div>

# Manticore

> **AI pentesting agent that finds the kill path, not just the vulnerabilities.**

Most security tools give you a list of findings. Manticore gives you the attack — the exact sequence of moves an adversary would chain together, the true combined severity, and a live proof-of-concept execution.

Powered by Qwen2.5-72B running on AMD Instinct MI300X GPUs via vLLM. Your codebase, your findings, and your LLM calls never leave your infrastructure.

---

## The Problem With Every Other AI Pentesting Tool

Run any scanner on a typical web app and you'll get something like this:

| ID | Finding | Severity | CVSS |
|----|---------|----------|------|
| 001 | Insecure Direct Object Reference | Medium | 6.5 |
| 002 | Session Token Exposed in URL | Low | 4.3 |
| 003 | Stored Cross-Site Scripting | Medium | 6.1 |

Three separate findings. Three separate tickets. Three separate remediation tasks.

What no tool tells you: **those three findings are one critical vulnerability.**

A real attacker doesn't go after vulnerabilities in isolation. They chain them. IDOR gives them a victim's user ID. The exposed session token lets them forge a session. The stored XSS payload runs in the victim's browser and exfiltrates everything. Total account takeover. Three moves. Sixty seconds.

Current tools — including AI-powered ones — score findings in isolation using CVSS theory. They never ask whether finding A makes finding B exploitable, or whether combining three mediums creates a critical. That gap is what Manticore closes.

---

## What Manticore Does Differently

After completing a full multi-phase pentest pipeline, Manticore runs a chain synthesis pass — feeding every finding simultaneously into a single long-context inference call on Qwen2.5-72B. The model reasons across the entire attack surface at once, identifies compound paths, and upgrades severity where chaining changes the real-world impact.

**Manticore output for the same three findings:**

```
MANTICORE-001  CRITICAL  CVSS 9.8
Attack Chain: Account Takeover via IDOR + Session Forgery + Stored XSS

Severity Upgrade:
  Before: 3 isolated findings (Medium, Low, Medium)
  After:  1 confirmed kill path (Critical)

Chain Steps:
  1. Extract victim user ID via IDOR at /api/user?id=<id>
  2. Forge session token using exposed URL parameter
  3. Deliver stored XSS payload — exfiltrates session to attacker

Impact: Complete compromise of any user account, including admin.
Proof of Concept: [Live Playwright execution included]
```

The severity upgrade card is the output that changes how security teams prioritize. Not theoretical. Not a heuristic. Proven by live browser execution.

---

## Pipeline

```
Target URL + Source Code
         │
         ▼
┌─────────────────────┐
│  Phase 1: Pre-Recon │  Deep source code analysis. Architecture mapping.
│                     │  Business context inference.
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  Phase 2: Recon     │  Live target exploration. Attack surface mapping.
│                     │  Endpoint discovery.
└────────┬────────────┘
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: Vulnerability Analysis (5 agents, parallel)       │
│  Injection · XSS · Auth · Authorization · SSRF              │
└────────┬────────────────────────────────────────────────────┘
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: Exploitation (5 agents, parallel)                 │
│  Real browser automation via Playwright. Proven PoCs only.  │
└────────┬────────────────────────────────────────────────────┘
         ▼
┌─────────────────────┐
│  Phase 5: Synthesis │  ← MANTICORE'S CORE — 3 specialist agents
│                     │
│  Chain Builder  →   │  Proposes compound attack paths from all findings
│  Validator      →   │  Independently challenges and approves each chain
│  Executor       →   │  Converts to exact Playwright steps + CVSS score
│                     │  All running on Qwen2.5-72B (AMD MI300X, 192GB VRAM)
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  Phase 6: Report    │  HackerOne-style report. Severity upgrade cards.
│                     │  Kill paths. Remediation. Live PoC attached.
└─────────────────────┘
```

---

## Why AMD MI300X Is Not Optional

The chain synthesis call sends everything at once: full codebase, all agent deliverables, recon findings, business context. That is 80,000 to 150,000 tokens in a single prompt.

The AMD Instinct MI300X provides 192GB of HBM3 VRAM and 5.3 TB/s memory bandwidth. Qwen2.5-72B fits entirely in VRAM at this scale, processes the full context in one pass without chunking, and returns a coherent chain analysis in seconds — not minutes.

Chunking this context destroys the reasoning. If you split findings across multiple calls, the model cannot see that finding A enables finding B. The chain disappears. The whole point of Manticore is the single-pass, full-context synthesis — and that only works at this VRAM scale.

This is not "we ran inference on AMD." The AMD hardware is the reason the feature is possible.

---

## Stack

| Component | Technology |
|-----------|-----------|
| GPU | AMD Instinct MI300X via AMD Developer Cloud |
| Inference | vLLM 0.17.1 on ROCm 7.2 |
| Model | Qwen2.5-72B-Instruct (open source, local) |
| Orchestration | Temporal (durable workflow engine) |
| Browser Automation | Playwright (real exploit execution) |
| Agent Framework | Claude Agent SDK (tool use + reasoning) |
| Language | TypeScript (Node.js 22) |

---

## Quick Start

**Prerequisites:** Docker, AMD Developer Cloud account with MI300X access, Node.js 22, pnpm, Python 3.10+

### Step 1 — Spin up vLLM on AMD Developer Cloud

Create a GPU droplet (MI300X, vLLM image) on [AMD Developer Cloud](https://cloud.amd.com), then SSH in and run:

```bash
# Pull and serve Qwen2.5-72B (fits in 192GB VRAM)
vllm serve Qwen/Qwen2.5-72B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 131072

# Verify it's running
curl http://localhost:8000/v1/models
```

### Step 2 — Clone and configure Manticore

```bash
git clone https://github.com/Deez-Automations/manticore
cd manticore

# Point to your AMD droplet
export ANTHROPIC_BASE_URL=http://<your-droplet-ip>:8000/v1
export ANTHROPIC_API_KEY=placeholder
export ANTHROPIC_MEDIUM_MODEL=Qwen/Qwen2.5-72B-Instruct
export ANTHROPIC_LARGE_MODEL=Qwen/Qwen2.5-72B-Instruct

# Install Python dependencies for chain synthesis
pip install -r manticore_engine/requirements.txt
```

### Step 3 — Run the pentest pipeline

```bash
# Build the Docker worker image
./manticore build

# Run full pipeline against target
./manticore start -u <target-url> -r <path-to-repo>
```

### Step 4 — Run Manticore chain synthesis

After Shannon's pipeline completes, run the chain synthesis engine:

```bash
# Point to the workspace deliverables from the completed scan
python manticore_engine/run.py ./workspaces/<workspace-name>/deliverables <target-url>
```

**Output:**
- `manticore_chains.json` — raw chain data with severity upgrades
- `manticore_report.md` — full HackerOne-style security assessment report

### Full Example (DVWA)

```bash
# Start DVWA locally
docker run -d -p 80:80 vulnerables/web-dvwa

# Run Manticore full pipeline
export ANTHROPIC_BASE_URL=http://<amd-droplet-ip>:8000/v1
export ANTHROPIC_API_KEY=placeholder
export ANTHROPIC_MEDIUM_MODEL=Qwen/Qwen2.5-72B-Instruct
export ANTHROPIC_LARGE_MODEL=Qwen/Qwen2.5-72B-Instruct

./manticore start -u http://localhost:80 -r ./dvwa-repo -w dvwa-scan
python manticore_engine/run.py ./workspaces/dvwa-scan/deliverables http://localhost:80
```

---

## Use Cases

- **Red team engagements** — move beyond isolated CVEs to full attack narratives
- **Bug bounty** — synthesize your recon into HackerOne-ready chain reports
- **Security engineering** — understand true compound risk before an attacker does
- **AppSec reviews** — prove that three low/medium findings are actually one critical

---

## Security & Privacy

Manticore runs entirely on your own infrastructure. Source code, findings, and LLM calls stay on your AMD cloud instance. Nothing is sent to external APIs. This is the core privacy argument for on-premise AI security tooling — and the reason enterprises cannot use cloud-based AI pentesting tools.

> **Authorized use only.** Run Manticore only on systems you own or have explicit written permission to test.

---

## License

AGPL v3 — see [LICENSE](./LICENSE)

Built at the AMD Developer Hackathon 2026 by [Muhammad Daniyal](https://github.com/Deez-Automations).
