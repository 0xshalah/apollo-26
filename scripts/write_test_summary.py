"""Turn a pytest JUnit XML report into ``docs/test-summary.json``.

The daemon publishes this file as the console's ``test.summary`` event
(contracts/websocket-events.schema.json). Counts come only from the test
runner's report; nothing here invents or rounds results.

    python scripts/write_test_summary.py --junit telemetry/state/pbt-full.xml \
        --profile full --report-path docs/pbt-report.md --out docs/test-summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path


def summarize(junit_xml: Path, profile: str, report_path: str) -> dict[str, object]:
    root = ET.parse(junit_xml).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise ValueError(f"{junit_xml} contains no <testsuite>")
    total = failed = skipped = 0
    for suite in suites:
        total += int(suite.get("tests", 0))
        failed += int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
    passed = total - failed - skipped
    if passed < 0:
        raise ValueError(f"inconsistent JUnit counts in {junit_xml}")
    return {
        "profile": profile,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "report_path": report_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    summary = summarize(args.junit, args.profile, args.report_path)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_name(f".{args.out.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.out)
    print(f"wrote {args.out}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
