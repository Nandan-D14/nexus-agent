# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""CLI for the 25-task production eval and release gate.

Examples:
    python -m nexus.eval.run_task_eval validate
    python -m nexus.eval.run_task_eval contract --output reports/contract.json
    python -m nexus.eval.run_task_eval score observations.json --output reports/candidate.json
    python -m nexus.eval.run_task_eval live my_adapter:execute --output reports/live.json
    python -m nexus.eval.run_task_eval gate baseline.json candidate.json
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sys
from typing import Any

from nexus.eval.production_suite import (
    TaskRunObservation,
    build_report,
    compare_reports,
    contract_observations,
    read_report,
    run_suite,
    write_report,
)
from nexus.eval.task_cases import TASK_CASES, validate_catalog


def _run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _load_executor(spec: str):
    if ":" not in spec:
        raise ValueError("executor must use module.path:callable syntax")
    module_name, attribute = spec.rsplit(":", 1)
    executor = getattr(importlib.import_module(module_name), attribute)
    if not callable(executor):
        raise TypeError(f"{spec} is not callable")
    return executor


def _load_observations(path: str) -> list[TaskRunObservation]:
    data: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("observations")
    if not isinstance(data, list):
        raise ValueError("observation input must be a list or {'observations': [...]} object")
    return [TaskRunObservation.from_dict(item) for item in data]


def _print_summary(report) -> None:
    summary = report.summary
    print(
        f"{report.run_id}: {summary.passed}/{summary.total} passed "
        f"({summary.success_rate:.1%}), critical "
        f"{summary.critical_passed}/{summary.critical_total}, "
        f"safety violations={summary.safety_violations}, "
        f"latency={summary.mean_latency_ms:.0f}ms, "
        f"cost=${summary.total_cost_usd:.4f}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CoComputer production task eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="validate the 25-case catalog")

    contract = subparsers.add_parser(
        "contract",
        help="exercise scorer and report schema with deterministic contract data",
    )
    contract.add_argument("--output", required=True)

    score = subparsers.add_parser("score", help="score recorded observations")
    score.add_argument("observations")
    score.add_argument("--output", required=True)
    score.add_argument("--run-id", default="")
    score.add_argument("--run-mode", default="live", choices=("live", "replay", "contract"))

    live = subparsers.add_parser("live", help="run all tasks through an executor adapter")
    live.add_argument("executor", help="async callable using module.path:callable")
    live.add_argument("--output", required=True)
    live.add_argument("--run-id", default="")

    gate = subparsers.add_parser("gate", help="compare candidate report to baseline")
    gate.add_argument("baseline")
    gate.add_argument("candidate")
    gate.add_argument("--output", default="")
    gate.add_argument(
        "--allow-contract",
        action="store_true",
        help="only for CI harness self-checks; never use for a release",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        validate_catalog()
        print(f"PASS: production eval catalog contains {len(TASK_CASES)} valid cases")
        return 0

    if args.command == "contract":
        report = build_report(
            contract_observations(),
            run_id=_run_id("contract"),
            run_mode="contract",
            metadata={"purpose": "harness-conformance-not-quality-baseline"},
        )
        write_report(report, args.output)
        _print_summary(report)
        return 0

    if args.command == "score":
        report = build_report(
            _load_observations(args.observations),
            run_id=args.run_id or _run_id("candidate"),
            run_mode=args.run_mode,
            metadata={"observations": str(Path(args.observations))},
        )
        write_report(report, args.output)
        _print_summary(report)
        return 0

    if args.command == "live":
        report = asyncio.run(
            run_suite(
                _load_executor(args.executor),
                run_id=args.run_id or _run_id("live"),
                run_mode="live",
                metadata={"executor": args.executor},
            )
        )
        write_report(report, args.output)
        _print_summary(report)
        return 0

    baseline = read_report(args.baseline)
    candidate = read_report(args.candidate)
    result = compare_reports(
        baseline,
        candidate,
        allow_contract=args.allow_contract,
    )
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
    for warning in result.warnings:
        print(f"WARN: {warning}")
    if result.passed:
        print("PASS: candidate meets or exceeds baseline release gates")
        return 0
    for reason in result.reasons:
        print(f"FAIL: {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
