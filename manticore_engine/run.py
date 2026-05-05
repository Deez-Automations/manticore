"""
Manticore — Entry point

Multi-agent pipeline:
  Queen orchestrates Chain Builder → Validator → Executor
  Then generates HackerOne-style report.

Usage:
  python run.py <deliverables_dir> <target_url>
"""

import sys
import os
import json
from agents import run_queen
from synthesize import load_findings, load_app_context, format_findings_for_prompt
from report import generate_report


def main():
    if len(sys.argv) < 3:
        print("Usage: python run.py <deliverables_dir> <target_url>")
        sys.exit(1)

    deliverables_dir = sys.argv[1]
    target_url = sys.argv[2]
    chains_path = os.path.join(deliverables_dir, "manticore_chains.json")
    report_path = os.path.join(deliverables_dir, "manticore_report.md")

    print("\n" + "="*60)
    print("  MANTICORE — Multi-Agent Attack Chain Synthesis")
    print("  AMD MI300X + Qwen2.5-72B via vLLM")
    print("="*60 + "\n")

    findings = load_findings(deliverables_dir)
    if not findings:
        print("[Manticore] No findings. Run the pentest pipeline first.")
        sys.exit(1)

    total = sum(len(v) for v in findings.values())
    print(f"[Manticore] {total} findings across {len(findings)} vuln classes\n")

    app_context = load_app_context(deliverables_dir)
    findings_text = format_findings_for_prompt(findings)

    final_chains = run_queen(app_context, findings_text)

    critical = sum(1 for c in final_chains if c.get("severity") == "CRITICAL")
    high = sum(1 for c in final_chains if c.get("severity") == "HIGH")

    chains_output = {
        "chains": final_chains,
        "total_chains": len(final_chains),
        "critical_count": critical,
        "high_count": high,
    }

    with open(chains_path, "w") as f:
        json.dump(chains_output, f, indent=2)

    print(f"\n[Manticore] {len(final_chains)} chain(s) | {critical} CRITICAL | {high} HIGH")

    print("[Manticore] Generating report...")
    generate_report(chains_path, deliverables_dir, target_url, report_path)

    print("\n" + "="*60)
    print(f"  Chains: {chains_path}")
    print(f"  Report: {report_path}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
