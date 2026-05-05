"""
Manticore — Entry point

Runs chain synthesis + report generation after Shannon completes.

Usage:
  python run.py <deliverables_dir> <target_url>

Example:
  python run.py ./workspaces/dvwa_abc123/deliverables http://localhost:80
"""

import sys
import os
from synthesize import synthesize
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
    print("  MANTICORE — Chain Synthesis Engine")
    print("  AMD MI300X + Qwen2.5-72B via vLLM")
    print("="*60 + "\n")

    print("[1/2] Running chain synthesis...")
    chains = synthesize(deliverables_dir, chains_path)

    total = chains.get("total_chains", 0)
    critical = chains.get("critical_count", 0)

    print(f"\n[Manticore] Results: {total} chain(s) | {critical} CRITICAL")
    if critical > 0:
        print("[Manticore] ⚠ CRITICAL chains identified — severity upgrades applied")

    print("\n[2/2] Generating HackerOne-style report...")
    generate_report(chains_path, deliverables_dir, target_url, report_path)

    print("\n" + "="*60)
    print(f"  Done. Report: {report_path}")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
