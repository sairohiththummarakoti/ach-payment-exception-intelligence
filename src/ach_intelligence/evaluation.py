import json
from typing import Any

from .config import Settings
from .fixtures import scenarios
from .intelligence import explain, interpret_return
from .knowledge import NOTES, VERSION, section_for
from .parser import parse


def evaluate() -> dict[str, Any]:
    results = []
    citation_checks = retrieval_checks = supported_claims = total_claims = 0
    reports = 0
    for case in scenarios():
        result = parse(case["data"])
        state = (
            "invalid"
            if any(f.severity == "error" for f in result.findings)
            else ("needs_review" if result.findings else "valid")
        )
        correct = state == case["expected_status"] and (
            case["expected_code"] is None
            or case["expected_code"] in {f.code for f in result.findings}
        )
        results.append(
            {
                "scenario": case["name"],
                "expected_status": case["expected_status"],
                "observed_status": state,
                "correct": correct,
            }
        )
        for index, finding in enumerate(result.findings):
            evidence_id = f"{case['name']}:{index}"
            report = explain(evidence_id, finding, Settings())
            reports += 1
            citation_checks += bool(report.citations) and all(
                c.section in NOTES and c.text == NOTES[c.section] and c.version == VERSION
                for c in report.citations
            )
            retrieval_checks += section_for(finding.code) in {c.section for c in report.citations}
            for claim in report.claims:
                total_claims += 1
                supported_claims += claim.evidence_ids == [evidence_id] and (
                    claim.text
                    == f"Validation recorded {finding.code} with severity {finding.severity}."
                    or (
                        finding.line is not None
                        and claim.text == f"The finding refers to source record {finding.line}."
                    )
                    or (
                        "expected" in finding.evidence
                        and "observed" in finding.evidence
                        and claim.text
                        == f"The computed value is {finding.evidence['expected']}; the control records {finding.evidence['observed']}."
                    )
                )
    return_cases = {"R01": True, "R02": True, "R03": True, "R04": True, "R29": True, "R99": False}
    return_correct = sum(interpret_return(k)["known"] == v for k, v in return_cases.items())
    correct_count = sum(r["correct"] for r in results)
    return {
        "fixture_set": "synthetic-ach-v1",
        "command": "uv run ach-demo evaluate",
        "mode": "offline; Moov and optional Ollama measured separately in integration tests",
        "validation": {
            "correct": correct_count,
            "total": len(results),
            "accuracy": correct_count / len(results),
        },
        "return_lookup": {"correct": return_correct, "total": len(return_cases)},
        "citations": {"reports_with_valid_citations": citation_checks, "total_reports": reports},
        "retrieval": {"relevant_section_present": retrieval_checks, "total_reports": reports},
        "claims": {
            "supported": supported_claims,
            "total": total_claims,
            "unsupported_rate": (total_claims - supported_claims) / max(1, total_claims),
        },
        "limitations": [
            "Small authored fixture suite; no population-level quality claim.",
            "Unsupported-claim metric checks fixed factual templates and evidence IDs; it is not a free-form LLM judge.",
            "Recommendations are a fixed two-step analyst checklist; no payment recommendation is generated.",
        ],
        "scenarios": results,
    }


def render() -> str:
    return json.dumps(evaluate(), indent=2)
