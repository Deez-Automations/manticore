# Manticore

**AI-powered attack chain synthesis for penetration testing. Finds the kill path, not just the vulnerabilities.**

Manticore is an autonomous AI pentesting agent that goes beyond isolated vulnerability detection. It analyzes your target's source code, runs a full multi-phase pentest pipeline, and synthesizes individual findings into compound attack chains — showing you the exact sequence of moves an attacker would use and the true combined severity.

Built on AMD MI300X GPUs running Qwen2.5-72B via vLLM. Local inference means your codebase and findings never leave your infrastructure.

---

## What Makes It Different

Every other AI pentesting tool gives you a list. Manticore gives you the attack.

**Standard output:**
- IDOR: Medium (CVSS 6.5)
- Session token in URL: Low (CVSS 4.3)
- Stored XSS: Medium (CVSS 6.1)

**Manticore output:**
- MANTICORE-001: **CRITICAL (9.8)** — Full account takeover via 3-step chain. Step 1: extract victim user ID via IDOR. Step 2: forge session token. Step 3: XSS payload exfiltrates auth. Live Playwright execution included.

---

## Architecture

- **Phase 1-2:** Pre-recon + recon (source code analysis + attack surface mapping)
- **Phase 3-4:** 5 parallel vulnerability agents + exploitation agents
- **Phase 5:** Chain synthesis — Manticore's core. Qwen2.5-72B reasons over all findings simultaneously in a single long-context pass, identifies compound attack paths, upgrades severity where chaining changes the real-world impact.
- **Phase 6:** Report with chain narratives + live Playwright PoC execution

---

## Stack

- AMD Instinct MI300X (192GB VRAM) via AMD Developer Cloud
- vLLM 0.17.1 on ROCm 7.2
- Qwen2.5-72B-Instruct (open source, local inference)
- Temporal (workflow orchestration)
- Playwright (browser automation + exploit execution)

---

## Quick Start

```bash
# Set your vLLM endpoint (AMD GPU droplet)
export ANTHROPIC_BASE_URL=http://<your-droplet-ip>:8000/v1
export ANTHROPIC_API_KEY=placeholder
export ANTHROPIC_MEDIUM_MODEL=Qwen/Qwen2.5-72B-Instruct
export ANTHROPIC_LARGE_MODEL=Qwen/Qwen2.5-72B-Instruct

# Run against a target
./manticore start -u <target-url> -r <path-to-repo>
```

---

## Based On

Manticore is built on top of [Shannon](https://github.com/KeygraphHQ/shannon) by Keygraph, licensed under AGPL v3. Manticore extends Shannon with GPU-accelerated long-context chain synthesis, open-source model support via vLLM, and AMD ROCm integration.

---

## License

AGPL v3 — see [LICENSE](./LICENSE)

Built at the AMD Developer Hackathon 2026 by [Muhammad Daniyal](https://github.com/Deez-Automations).
