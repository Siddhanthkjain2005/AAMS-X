"""Print a compact, computed summary of the bundled reproducible evidence."""

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    for path in sorted((ROOT / "data" / "demo").glob("BENCH-*.json")):
        report = json.loads(path.read_text())
        print(f"\n{report['id']}: {report['completed']} paired worlds · {report['config']['runs']} seeds · {report['config']['horizon']} slots")
        print("Scenario          Fixed recall    MAG-NTS recall    Vanilla TS recall")
        for scenario in report["config"]["scenarios"]:
            values = {a["algorithm"]: a["metrics"]["recall"]["mean"] for a in report["aggregates"] if a["scenario"] == scenario}
            print(f"{scenario:17} {values.get('fixed', 0):>10.2%} {values.get('magnts', 0):>16.2%} {values.get('thompson', 0):>19.2%}")
    periodic = ROOT / "data" / "demo" / "periodic-seed-42.json.gz"
    if periodic.exists():
        record = json.loads(gzip.decompress(periodic.read_bytes()))
        policy = record["frames"][-1]["policies"]["magnts"]
        print(f"\nPeriodic challenge {record['id']}:")
        print("Resolved forecasts:", policy["metrics"]["resolved_predictions"], "MAE (ms):", policy["metrics"]["avg_intercept_time_error_ms"])
        for candidate in policy["belief"]["periodicity"][:4]:
            print("Band", candidate["band"], "period", candidate["period_slots"], "slots; confidence", candidate["confidence"], "; observed episodes", candidate["evidence_count"])


if __name__ == "__main__":
    main()
