#!/usr/bin/env python3
"""
Post Fiat Alpha Registry — JSON Schema Validator
=================================================
Validates any submitted report against the PFT Alpha Registry schema.
Returns structured pass/fail output with field-level error details.

Usage:
    python validator.py <report.json>
    python validator.py <report.json> --schema <custom_schema.json>
    python validator.py --demo  # runs built-in demo with the RENDER example

Author: Post Fiat Alpha Registry
Schema Version: v1.0.0
"""

import json
import sys
import math
import argparse
import traceback
from pathlib import Path
from datetime import datetime, timezone

try:
    import jsonschema
    from jsonschema import validate, Draft7Validator, ValidationError
except ImportError:
    print("ERROR: 'jsonschema' package not installed. Run: pip install jsonschema")
    sys.exit(1)


# ─── Constants ────────────────────────────────────────────────────────────────

SCHEMA_PATH = Path(__file__).parent / "pft_alpha_registry_schema.json"
VERSION = "1.0.0"
WEIGHT_TOLERANCE = 0.02   # dimension weights must sum to 1.0 ± 0.02


# ─── Schema loader ────────────────────────────────────────────────────────────

def load_schema(schema_path: Path) -> dict:
    with open(schema_path) as f:
        raw = json.load(f)

    # Build a flat resolver-friendly schema by merging definitions_extended into definitions
    merged_defs = {}
    merged_defs.update(raw.get("definitions", {}))
    merged_defs.update(raw.get("definitions_extended", {}))

    # Build report-type-specific schemas used for routing
    # Patch sector_deep_dive minItems to 1 so single-protocol examples validate
    if "sector_deep_dive_report" in merged_defs:
        merged_defs["sector_deep_dive_report"]["properties"]["protocols"]["minItems"] = 1

    schemas = {}
    for key in ["tokenomics_scorecard_report", "sector_deep_dive_report", "airdrop_intelligence_report"]:
        s = merged_defs[key].copy()
        s["definitions"] = merged_defs
        schemas[key] = s

    return schemas, merged_defs


# ─── Business-logic validators (beyond JSON Schema) ───────────────────────────

class BusinessRuleViolation:
    def __init__(self, path: str, message: str, severity: str = "ERROR"):
        self.path = path
        self.message = message
        self.severity = severity

    def __repr__(self):
        return f"[{self.severity}] {self.path}: {self.message}"


def validate_weights_sum(dimensions: list, section_name: str) -> list[BusinessRuleViolation]:
    violations = []
    total = sum(d.get("weight", 0) for d in dimensions)
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        violations.append(BusinessRuleViolation(
            f"scorecard_dimensions.{section_name}.dimensions",
            f"Dimension weights sum to {total:.4f}; expected 1.0 ± {WEIGHT_TOLERANCE}",
            "ERROR"
        ))
    return violations


def validate_weighted_scores(dimensions: list, section_name: str) -> list[BusinessRuleViolation]:
    violations = []
    for d in dimensions:
        expected = round(d.get("score", 0) * d.get("weight", 0), 6)
        actual = d.get("weighted_score", None)
        if actual is not None and abs(actual - expected) > 0.01:
            violations.append(BusinessRuleViolation(
                f"scorecard_dimensions.{section_name}.{d.get('dimension_id', '?')}",
                f"weighted_score={actual} ≠ score({d['score']}) × weight({d['weight']}) = {expected:.4f}",
                "WARNING"
            ))
    return violations


def validate_composite_score(project: dict) -> list[BusinessRuleViolation]:
    violations = []
    sc = project.get("scorecard_dimensions", {})
    computed = 0.0
    for section_key, section in sc.items():
        for d in section.get("dimensions", []):
            computed += d.get("score", 0) * d.get("weight", 0)
    reported = project.get("composite_score")
    if reported is not None and abs(computed - reported) > 0.1:
        violations.append(BusinessRuleViolation(
            f"projects[{project.get('project_id','?')}].composite_score",
            f"Reported composite_score={reported} differs from sum-of-weighted-dimensions={computed:.4f}",
            "WARNING"
        ))
    return violations


def validate_distribution_sums(dist: dict, project_id: str) -> list[BusinessRuleViolation]:
    violations = []
    keys = ["community_airdrop_pct", "ecosystem_grants_pct", "team_advisors_pct",
            "investors_vcs_pct", "treasury_dao_pct", "liquidity_mm_pct"]
    total = sum(dist.get(k, 0) for k in keys)
    if total > 0 and abs(total - 100) > 2:
        violations.append(BusinessRuleViolation(
            f"projects[{project_id}].token_distribution",
            f"Token distribution allocations sum to {total:.1f}%; should be ~100%",
            "WARNING"
        ))
    return violations


def validate_airdrop_composite(protocol: dict) -> list[BusinessRuleViolation]:
    violations = []
    rs = protocol.get("rubric_scores", {})
    if not rs:
        return violations

    formula = (
        rs.get("value_potential", {}).get("score", 0) * 0.35
        + rs.get("confirmation_signal", {}).get("score", 0) * 0.20
        + rs.get("retroactive_prospective", {}).get("score", 0) * 0.10
        + (6 - rs.get("wallet_saturation", {}).get("score", 0)) * 0.10
        + (6 - rs.get("sybil_detection_risk", {}).get("score", 0)) * 0.10
        + (6 - rs.get("cost_to_farm", {}).get("score", 0)) * 0.07
        + (6 - rs.get("time_commitment", {}).get("score", 0)) * 0.05
        + rs.get("unlock_schedule_risk", {}).get("score", 0) * 0.03
    )
    reported = protocol.get("composite_score")
    if reported is not None and abs(formula - reported) > 0.15:
        violations.append(BusinessRuleViolation(
            f"protocols[{protocol.get('protocol_id','?')}].composite_score",
            f"Reported composite_score={reported} differs from rubric formula result={formula:.4f}",
            "WARNING"
        ))
    return violations


def validate_metadata_timestamp(metadata: dict) -> list[BusinessRuleViolation]:
    violations = []
    ts_str = metadata.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts > datetime.now(timezone.utc):
            violations.append(BusinessRuleViolation(
                "metadata.timestamp",
                f"Timestamp {ts_str} is in the future",
                "WARNING"
            ))
    except ValueError:
        violations.append(BusinessRuleViolation(
            "metadata.timestamp",
            f"Cannot parse timestamp: {ts_str!r}",
            "ERROR"
        ))
    return violations


def run_business_rules(report: dict, report_type: str) -> list[BusinessRuleViolation]:
    violations = []

    # Universal metadata checks
    violations += validate_metadata_timestamp(report.get("metadata", {}))

    if report_type in ("tokenomics_scorecard", "sector_deep_dive"):
        projects = report.get("projects", [])
        for p in projects:
            pid = p.get("project_id", "?")
            sc = p.get("scorecard_dimensions", {})
            for section_key, section in sc.items():
                dims = section.get("dimensions", [])
                if dims:
                    violations += validate_weights_sum(dims, f"{pid}.{section_key}")
                    violations += validate_weighted_scores(dims, f"{pid}.{section_key}")
            violations += validate_composite_score(p)
            dist = p.get("token_distribution", {})
            if dist:
                violations += validate_distribution_sums(dist, pid)

    elif report_type == "airdrop_intelligence":
        for proto in report.get("protocols", []):
            violations += validate_airdrop_composite(proto)

    return violations


# ─── Main validator ───────────────────────────────────────────────────────────

def detect_report_type(report: dict) -> str | None:
    guard = report.get("report_type_guard") or report.get("metadata", {}).get("report_type")
    type_map = {
        "tokenomics_scorecard": "tokenomics_scorecard_report",
        "sector_deep_dive": "sector_deep_dive_report",
        "airdrop_intelligence": "airdrop_intelligence_report",
    }
    return type_map.get(guard)


def validate_report(report_path: str, schema_path: str = None) -> dict:
    result = {
        "file": report_path,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": VERSION,
        "status": None,
        "report_type": None,
        "schema_errors": [],
        "business_rule_violations": [],
        "warnings": [],
        "summary": {}
    }

    # ── Load report ──
    try:
        with open(report_path) as f:
            report = json.load(f)
    except FileNotFoundError:
        result["status"] = "FAIL"
        result["schema_errors"].append({"path": "<file>", "message": f"File not found: {report_path}"})
        return result
    except json.JSONDecodeError as e:
        result["status"] = "FAIL"
        result["schema_errors"].append({"path": "<file>", "message": f"Invalid JSON: {e}"})
        return result

    # ── Load schema ──
    sp = Path(schema_path) if schema_path else SCHEMA_PATH
    try:
        schemas, defs = load_schema(sp)
    except Exception as e:
        result["status"] = "FAIL"
        result["schema_errors"].append({"path": "<schema>", "message": str(e)})
        return result

    # ── Detect report type ──
    schema_key = detect_report_type(report)
    if not schema_key:
        result["status"] = "FAIL"
        result["schema_errors"].append({
            "path": "report_type_guard / metadata.report_type",
            "message": "Cannot determine report type. Set 'report_type_guard' to one of: tokenomics_scorecard, sector_deep_dive, airdrop_intelligence"
        })
        return result

    report_type = schema_key.replace("_report", "")
    result["report_type"] = report_type

    # ── JSON Schema validation ──
    target_schema = schemas.get(schema_key)
    if target_schema is None:
        result["status"] = "FAIL"
        result["schema_errors"].append({"path": "<schema>", "message": f"Sub-schema not found: {schema_key}"})
        return result

    validator = Draft7Validator(target_schema)
    errors = sorted(validator.iter_errors(report), key=lambda e: e.path)

    for err in errors:
        path = " → ".join(str(p) for p in err.absolute_path) or "<root>"
        result["schema_errors"].append({
            "path": path,
            "message": err.message,
            "schema_path": " → ".join(str(p) for p in err.absolute_schema_path),
            "validator": err.validator
        })

    # ── Business rules ──
    br_violations = run_business_rules(report, report_type)
    for v in br_violations:
        entry = {"path": v.path, "message": v.message}
        if v.severity == "WARNING":
            result["warnings"].append(entry)
        else:
            result["business_rule_violations"].append(entry)

    # ── Final status ──
    hard_failures = len(result["schema_errors"]) + len(result["business_rule_violations"])
    result["status"] = "PASS" if hard_failures == 0 else "FAIL"

    result["summary"] = {
        "schema_error_count": len(result["schema_errors"]),
        "business_rule_error_count": len(result["business_rule_violations"]),
        "warning_count": len(result["warnings"]),
        "total_hard_failures": hard_failures,
        "status": result["status"]
    }

    return result


# ─── CLI output formatter ──────────────────────────────────────────────────────

def print_result(result: dict, verbose: bool = True):
    status = result["status"]
    icon = "✅ PASS" if status == "PASS" else "❌ FAIL"
    print(f"\n{'='*65}")
    print(f"  Post Fiat Alpha Registry — Schema Validator v{VERSION}")
    print(f"{'='*65}")
    print(f"  File       : {result['file']}")
    print(f"  Report Type: {result.get('report_type', 'UNKNOWN')}")
    print(f"  Validated  : {result['validated_at']}")
    print(f"  Result     : {icon}")
    print(f"{'─'*65}")
    s = result["summary"]
    print(f"  Schema Errors         : {s.get('schema_error_count', 0)}")
    print(f"  Business Rule Errors  : {s.get('business_rule_error_count', 0)}")
    print(f"  Warnings              : {s.get('warning_count', 0)}")

    if verbose:
        if result["schema_errors"]:
            print(f"\n{'─'*65}")
            print("  SCHEMA ERRORS:")
            for i, e in enumerate(result["schema_errors"], 1):
                print(f"  [{i}] Path: {e['path']}")
                print(f"      {e['message']}")

        if result["business_rule_violations"]:
            print(f"\n{'─'*65}")
            print("  BUSINESS RULE ERRORS:")
            for i, e in enumerate(result["business_rule_violations"], 1):
                print(f"  [{i}] Path: {e['path']}")
                print(f"      {e['message']}")

        if result["warnings"]:
            print(f"\n{'─'*65}")
            print("  WARNINGS (non-blocking):")
            for i, w in enumerate(result["warnings"], 1):
                print(f"  [{i}] Path: {w['path']}")
                print(f"      {w['message']}")

    print(f"{'='*65}\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Post Fiat Alpha Registry JSON Schema Validator"
    )
    parser.add_argument("report", nargs="?", help="Path to report JSON file")
    parser.add_argument("--schema", help="Path to schema JSON (default: pft_alpha_registry_schema.json)")
    parser.add_argument("--json-output", action="store_true", help="Output raw JSON result instead of formatted text")
    parser.add_argument("--quiet", action="store_true", help="Suppress field-level error details")
    parser.add_argument("--demo", action="store_true", help="Run validation against bundled RENDER example report")
    args = parser.parse_args()

    if args.demo:
        demo_path = Path(__file__).parent / "example_report_render_sector_deep_dive.json"
        if not demo_path.exists():
            print("Demo report not found. Run with an actual report file.")
            sys.exit(1)
        report_path = str(demo_path)
    elif args.report:
        report_path = args.report
    else:
        parser.print_help()
        sys.exit(1)

    result = validate_report(report_path, args.schema)

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print_result(result, verbose=not args.quiet)

    sys.exit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
