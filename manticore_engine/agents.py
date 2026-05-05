"""
Manticore Multi-Agent Orchestration

Queen pattern: orchestrator coordinates 3 specialist agents running
on Qwen2.5-72B via vLLM on AMD MI300X. Each agent is a separate
inference call with a focused role.

Flow:
  Queen → Chain Builder → Validator → Executor → Final Output
"""

import json
import os
from openai import OpenAI

VLLM_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "http://localhost:8000/v1").replace("/v1", "") + "/v1"
MODEL = os.environ.get("ANTHROPIC_MEDIUM_MODEL", "Qwen/Qwen2.5-72B-Instruct")

client = OpenAI(base_url=VLLM_BASE_URL, api_key="placeholder")


def call(system: str, user: str, temperature: float = 0.1, max_tokens: int = 4096) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def parse_json(raw: str) -> dict:
    import re
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse JSON from model output:\n{raw[:300]}")


# ── Agent 1: Chain Builder ────────────────────────────────────────────────────

CHAIN_BUILDER_SYSTEM = """You are an elite red team operator specializing in attack chain construction.

Your job: given a list of security findings, identify which vulnerabilities can be chained together to achieve maximum impact.

Think step by step:
1. What does each finding give an attacker? (information, access, execution?)
2. Which findings enable other findings? (finding A gives data needed for finding B)
3. What is the worst-case end state an attacker can reach by chaining findings?
4. What is the minimum number of steps to get there?

Output only valid JSON. No explanation outside the JSON."""

CHAIN_BUILDER_PROMPT = """Application context:
{app_context}

Security findings:
{findings}

Build all viable attack chains. Return JSON:
{{
  "chains": [
    {{
      "id": "CHAIN-001",
      "title": "descriptive title",
      "findings_used": ["FINDING-001", "FINDING-003"],
      "end_state": "what attacker achieves",
      "steps": ["step 1", "step 2", "step 3"],
      "affected_endpoints": ["/api/user"],
      "estimated_severity": "CRITICAL|HIGH|MEDIUM"
    }}
  ]
}}"""


# ── Agent 2: Validator ────────────────────────────────────────────────────────

VALIDATOR_SYSTEM = """You are a senior penetration tester reviewing another tester's attack chains.

Your job: validate or reject each chain. Be skeptical. Challenge assumptions.

For each chain ask:
- Are all findings real and present in the findings list?
- Is each step actually achievable given the app's architecture?
- Does chaining these findings genuinely increase severity or is it theoretical?
- Are the steps in the right order? Does step N actually enable step N+1?

Reject chains that are speculative. Approve only chains you would stake your reputation on.

Output only valid JSON."""

VALIDATOR_PROMPT = """Original findings:
{findings}

Proposed chains from Chain Builder:
{chains}

Validate each chain. Return JSON:
{{
  "validated_chains": [
    {{
      "id": "CHAIN-001",
      "approved": true,
      "confidence": "HIGH|MEDIUM|LOW",
      "rejection_reason": null,
      "revised_steps": ["step 1 revised if needed"],
      "validator_notes": "brief note on why this chain is valid"
    }}
  ]
}}"""


# ── Agent 3: Executor ─────────────────────────────────────────────────────────

EXECUTOR_SYSTEM = """You are a penetration tester who specializes in writing precise exploitation steps.

Your job: take a validated attack chain and convert it into exact, executable steps that a Playwright browser automation script can follow.

Each step must be:
- A single browser action (navigate, click, fill, extract, submit)
- Specific about the selector, URL, or value used
- In the correct sequence

Also assign the final CVSS score based on the chain's actual impact.

Output only valid JSON."""

EXECUTOR_PROMPT = """Application context:
{app_context}

Validated attack chain:
{chain}

Convert to executable Playwright steps and assign CVSS. Return JSON:
{{
  "id": "MANTICORE-001",
  "title": "chain title",
  "severity": "CRITICAL",
  "cvss_score": 9.8,
  "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
  "cwe_ids": ["CWE-639"],
  "severity_before": {{
    "ratings": ["Medium (6.5)", "Low (4.3)"],
    "highest": "Medium (6.5)"
  }},
  "severity_after": "CRITICAL (9.8)",
  "summary": "one paragraph summary",
  "impact": "what attacker achieves",
  "playwright_steps": [
    {{"action": "navigate", "url": "http://target/api/user?id=1", "note": "enumerate user IDs via IDOR"}},
    {{"action": "fill", "selector": "#username", "value": "victim@example.com", "note": "use extracted email"}},
    {{"action": "extract", "selector": "#session-token", "store_as": "token", "note": "grab exposed token from URL"}}
  ],
  "affected_endpoints": ["/api/user"],
  "remediation": "specific fix for this chain"
}}"""


# ── Queen Orchestrator ────────────────────────────────────────────────────────

def run_queen(app_context: str, findings_text: str) -> list[dict]:
    print("[Queen] Dispatching Chain Builder agent...")
    raw_chains = call(
        system=CHAIN_BUILDER_SYSTEM,
        user=CHAIN_BUILDER_PROMPT.format(app_context=app_context, findings=findings_text),
        temperature=0.2,
    )
    chains = parse_json(raw_chains)
    print(f"[Chain Builder] Proposed {len(chains.get('chains', []))} chain(s)")

    print("[Queen] Dispatching Validator agent...")
    raw_validation = call(
        system=VALIDATOR_SYSTEM,
        user=VALIDATOR_PROMPT.format(findings=findings_text, chains=json.dumps(chains, indent=2)),
        temperature=0.1,
    )
    validation = parse_json(raw_validation)

    approved = [v for v in validation.get("validated_chains", []) if v.get("approved")]
    print(f"[Validator] {len(approved)}/{len(chains.get('chains', []))} chain(s) approved")

    approved_ids = {v["id"] for v in approved}
    approved_chains = [c for c in chains.get("chains", []) if c["id"] in approved_ids]

    final_chains = []
    for i, chain in enumerate(approved_chains):
        manticore_id = f"MANTICORE-{i+1:03d}"
        print(f"[Queen] Dispatching Executor agent for {chain['id']}...")
        raw_exec = call(
            system=EXECUTOR_SYSTEM,
            user=EXECUTOR_PROMPT.format(app_context=app_context, chain=json.dumps(chain, indent=2)),
            temperature=0.1,
        )
        executed = parse_json(raw_exec)
        executed["id"] = manticore_id
        final_chains.append(executed)
        print(f"[Executor] {manticore_id} ready — {executed.get('severity')} ({executed.get('cvss_score')})")

    return final_chains
