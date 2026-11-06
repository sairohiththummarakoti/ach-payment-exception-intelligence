import argparse
import json
from pathlib import Path

import httpx

from .config import Settings
from .db import make_engine, migrate
from .evaluation import evaluate
from .fixtures import generate, make_file, mutate
from .schemas import ReviewRequest
from .service import explain_exception, ingest, review


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic ACH demo and evaluation")
    parser.add_argument("command", choices=["generate", "evaluate", "demo", "smoke", "migrate"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    args = parser.parse_args()
    if args.command == "generate":
        print(
            json.dumps({"generated": len(generate(args.output or Path("data/fixtures")))}, indent=2)
        )
        return
    if args.command == "evaluate":
        report = evaluate()
        result = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result, encoding="utf-8")
        print(result)
        if (
            report["validation"]["correct"] != report["validation"]["total"]
            or report["claims"]["unsupported_rate"]
            or report["return_lookup"]["correct"] != report["return_lookup"]["total"]
            or report["citations"]["reports_with_valid_citations"]
            != report["citations"]["total_reports"]
            or report["retrieval"]["relevant_section_present"]
            != report["retrieval"]["total_reports"]
        ):
            raise SystemExit(1)
        return
    config = Settings()
    if args.command == "smoke":
        headers = {"X-Synthetic-Data": "true"}
        if config.api_token:
            headers["Authorization"] = "Bearer " + config.api_token
        with httpx.Client(base_url=args.url, headers=headers, timeout=30) as client:
            client.get("/health").raise_for_status()
            valid = client.post(
                "/api/v1/ach/files", files={"file": ("valid.ach", make_file(), "text/plain")}
            )
            valid.raise_for_status()
            assert valid.json()["validation_status"] in {"valid", "needs_review"}, valid.text
            bad = client.post(
                "/api/v1/ach/files",
                files={
                    "file": (
                        "bad.ach",
                        mutate(make_file(), 4, 32, 44, "000000000001"),
                        "text/plain",
                    )
                },
            )
            bad.raise_for_status()
            result = bad.json()
            exception = next(e for e in result["exceptions"] if e["code"] == "BATCH_CREDIT_TOTAL")
            response = client.post(f"/api/v1/ach/exceptions/{exception['id']}/explain")
            response.raise_for_status()
            assert response.json()["citations"]
            disposition = client.post(
                f"/api/v1/ach/exceptions/{exception['id']}/review",
                json={
                    "action": "comment",
                    "reviewer": "demo-analyst",
                    "comment": "Synthetic smoke verification",
                    "expected_version": exception["version"],
                },
            )
            disposition.raise_for_status()
            audit = client.get(f"/api/v1/ach/files/{result['id']}/audit")
            audit.raise_for_status()
            assert any(e["action"] == "comment" for e in audit.json())
            print(
                json.dumps(
                    {
                        "health": "passed",
                        "valid_file_id": valid.json()["id"],
                        "invalid_file_id": result["id"],
                        "explanation": "cited",
                        "audit": "persisted",
                    },
                    indent=2,
                )
            )
        return
    engine = make_engine(config.database_url)
    migrate(engine)
    if args.command == "migrate":
        print("Schema upgraded to 0001")
    else:
        file = ingest(engine, config, mutate(make_file(), 4, 32, 44, "000000000001"))
        exception = next(e for e in file["exceptions"] if e["code"] == "BATCH_CREDIT_TOTAL")
        report = explain_exception(engine, config, exception["id"])
        decision = review(
            engine,
            exception["id"],
            ReviewRequest(
                action="comment",
                reviewer="demo-analyst",
                comment="Control mismatch requires investigation",
                expected_version=exception["version"],
            ),
        )
        print(json.dumps({"file": file, "explanation": report, "review": decision}, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
