from types import SimpleNamespace

from bson import ObjectId
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class FakeTicketCollection:
    def __init__(self, records=None):
        self.records = list(records or [])

    def find(self, query=None):
        return [dict(record) for record in self.records]

    def find_one(self, query):
        for record in self.records:
            if record.get("_id") == query.get("_id"):
                return dict(record)
        return None

    def insert_one(self, document):
        document["_id"] = document.get("_id") or ObjectId()
        self.records.append(document.copy())
        return SimpleNamespace(inserted_id=document["_id"])

    def update_one(self, query, update):
        for record in self.records:
            if record.get("_id") == query.get("_id"):
                if "$set" in update:
                    record.update(update["$set"])
                if "$push" in update:
                    for key, value in update["$push"].items():
                        record.setdefault(key, []).append(value)
                return None
        raise KeyError("record not found")

    def aggregate(self, pipeline):
        if pipeline and pipeline[0].get("$group", {}).get("_id") == "$status":
            buckets = {}
            for record in self.records:
                buckets[record["status"]] = buckets.get(record["status"], 0) + 1
            return [{"_id": status, "count": count} for status, count in buckets.items()]
        return []


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_and_reporting(monkeypatch):
    records = [
        {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Login failure",
            "status": "open",
            "priority": "high",
            "category": "access",
            "created_at": "2025-01-01T09:30:00Z",
        },
        {
            "_id": ObjectId("507f1f77bcf86cd799439012"),
            "title": "Billing delay",
            "status": "resolved",
            "priority": "medium",
            "category": "billing",
            "created_at": "2025-01-02T10:00:00Z",
        },
    ]

    monkeypatch.setattr("app.main.get_collection", lambda name: FakeTicketCollection(records) if name == "tickets" else FakeTicketCollection())

    login_response = client.post(
        "/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["token"]

    summary_response = client.get(
        "/reports/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert summary_response.status_code == 200
    payload = summary_response.json()
    assert payload["total_tickets"] == 2
    assert payload["open_tickets"] == 1
    assert payload["in_progress_tickets"] == 0
    assert payload["status_breakdown"][0]["_id"] == "open"


def test_incident_lifecycle_requires_login(monkeypatch):
    collection = FakeTicketCollection()
    monkeypatch.setattr("app.main.get_collection", lambda name: collection)

    assert client.post("/incidents", json={"title": "Cannot access event report"}).status_code == 401

    token = client.post(
        "/login",
        json={"username": "admin", "password": "admin123"},
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/incidents",
        headers=headers,
        json={
            "title": "Cannot access event report",
            "category": "reporting",
            "priority": "high",
            "description": "The event report returns an error after sign-in.",
            "owner": "support-team",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "open"

    ticket_id = created.json()["id"]
    in_progress = client.patch(
        f"/incidents/{ticket_id}",
        headers=headers,
        json={"status": "in-progress"},
    )
    assert in_progress.status_code == 200
    assert in_progress.json()["status"] == "in-progress"
    summary = client.get("/reports/summary", headers=headers).json()
    assert summary["in_progress_tickets"] == 1

    resolved = client.patch(
        f"/incidents/{ticket_id}",
        headers=headers,
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    summary = client.get("/reports/summary", headers=headers).json()
    assert summary["resolved_tickets"] == 1
    assert summary["in_progress_tickets"] == 0
