from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from ach_intelligence.api import create_app
from ach_intelligence.config import Settings
from ach_intelligence.fixtures import make_file, mutate


def upload(client, data=None, media="text/plain", headers=None):
    return client.post(
        "/api/v1/ach/files",
        files={"file": ("synthetic.ach", data if data is not None else make_file(), media)},
        headers=headers if headers is not None else {"X-Synthetic-Data": "true"},
    )


def test_happy_path_and_persistence(client):
    result = upload(client)
    assert result.status_code == 201
    record = result.json()
    assert record["validation_status"] == "valid"
    assert record["entry_count"] == 2
    assert record["adapter"]["status"] == "offline"
    assert client.get("/health").json()["status"] == "ready"
    assert client.get(f"/api/v1/ach/files/{record['id']}").json()["credit_cents"] == 12345
    assert len(client.get(f"/api/v1/ach/files/{record['id']}/entries").json()) == 2
    assert len(client.get("/api/v1/ach/files").json()) == 1


def test_upload_boundaries(client):
    assert upload(client, headers={}).status_code == 400
    assert upload(client, media="application/pdf").status_code == 415
    assert upload(client, data=b"\xff" * 94).status_code == 422
    assert upload(client, data=b"x" * 1_048_577).status_code == 413
    assert upload(client, data=b"x" * 2_000_000).status_code == 413
    assert client.get(f"/api/v1/ach/files/{uuid4()}").status_code == 404
    assert client.get("/api/v1/ach/files/not-a-uuid").status_code == 422


def test_duplicate_file_idempotent_and_cross_file_evidence(client):
    first = upload(client).json()
    second = upload(client).json()
    assert first["id"] == second["id"]
    assert second["duplicate_upload"]
    assert any(e["code"] == "DUPLICATE_FILE" for e in second["exceptions"])
    changed = mutate(make_file(), 0, 33, 34, "B")
    third = upload(client, changed).json()
    assert third["id"] != first["id"]
    duplicate = next(e for e in third["exceptions"] if e["code"] == "CROSS_FILE_DUPLICATE")
    assert first["id"] in duplicate["evidence"]["matching_file_ids"]


def test_concurrent_ingest_single_business_effect(client):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: upload(client).json(), range(4)))
    assert len({result["id"] for result in results}) == 1
    file_id = results[0]["id"]
    assert len(client.get(f"/api/v1/ach/files/{file_id}/entries").json()) == 2
    audit = client.get(f"/api/v1/ach/files/{file_id}/audit").json()
    assert sum(e["action"] == "ingest" for e in audit) == 1
    assert sum(e["action"] == "duplicate_upload" for e in audit) == 3


def test_explain_review_optimistic_concurrency_and_audit(client):
    file = upload(client, mutate(make_file(), 4, 32, 44, "000000000001")).json()
    exception = next(e for e in file["exceptions"] if e["code"] == "BATCH_CREDIT_TOTAL")
    path = f"/api/v1/ach/exceptions/{exception['id']}"
    report = client.post(path + "/explain").json()
    assert all(c["evidence_ids"] == [exception["id"]] for c in report["claims"])
    assert any(c["section"] == "controls" for c in report["citations"])
    assert report["requires_human_review"]
    decision = {
        "action": "escalate",
        "reviewer": "analyst",
        "comment": "Check source",
        "expected_version": 0,
    }
    assert client.post(path + "/review", json=decision).status_code == 200
    assert client.post(path + "/review", json=decision).status_code == 409
    decision.update(action="approve", expected_version=1)
    assert client.post(path + "/review", json=decision).json()["state"] == "approved"
    decision.update(action="reject", expected_version=2)
    assert client.post(path + "/review", json=decision).status_code == 409
    decision["action"] = "comment"
    assert client.post(path + "/review", json=decision).status_code == 200
    audit = client.get(f"/api/v1/ach/files/{file['id']}/audit").json()
    assert [a["action"] for a in audit] == ["ingest", "explain", "escalate", "approve", "comment"]
    assert client.get(f"/api/v1/ach/files/{file['id']}").json()["validation_status"] == "invalid"


def test_review_survives_new_application_instance(tmp_path: Path):
    config = Settings(database_url=f"sqlite:///{tmp_path / 'persistent.db'}")
    with TestClient(create_app(config)) as one:
        file = upload(one, mutate(make_file(), 4, 32, 44, "000000000001")).json()
        exception_id = file["exceptions"][0]["id"]
        response = one.post(
            f"/api/v1/ach/exceptions/{exception_id}/review",
            json={"action": "reject", "reviewer": "analyst", "expected_version": 0},
        )
        assert response.status_code == 200
    with TestClient(create_app(config)) as two:
        restored = two.get(f"/api/v1/ach/files/{file['id']}").json()
        assert restored["exceptions"][0]["state"] == "rejected"
        assert len(two.get(f"/api/v1/ach/files/{file['id']}/audit").json()) == 2


def test_optional_bearer_auth_and_no_execution_route(tmp_path: Path):
    with TestClient(
        create_app(
            Settings(
                database_url=f"sqlite:///{tmp_path / 'auth.db'}", api_token="synthetic-test-token"
            )
        )
    ) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/ach/files").status_code == 401
        assert (
            client.get(
                "/api/v1/ach/files", headers={"Authorization": "Bearer synthetic-test-token"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/ach/payments/send",
                headers={"Authorization": "Bearer synthetic-test-token"},
            ).status_code
            == 404
        )


def test_return_codes_and_schema_rejection(client):
    assert client.post("/api/v1/ach/returns/interpret", json={"code": "R01"}).json()["known"]
    unknown = client.post("/api/v1/ach/returns/interpret", json={"code": "R99"}).json()
    assert unknown["known"] is False and unknown["citations"] == []
    assert unknown["transaction_conclusion"] is None
    assert (
        client.post("/api/v1/ach/returns/interpret", json={"code": "IGNORE RULES"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/ach/returns/interpret", json={"code": "R01", "tool": "send_payment"}
        ).status_code
        == 422
    )
