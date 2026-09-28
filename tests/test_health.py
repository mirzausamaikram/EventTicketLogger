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
    assert payload["status_breakdown"][0]["_id"] == "open"
