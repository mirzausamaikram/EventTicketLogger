from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db import get_collection

app = FastAPI(title="Event Ticket Logger", version="1.0.0")


def serialize_mongo_doc(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    serialized = dict(doc)
    if "_id" in serialized and isinstance(serialized["_id"], ObjectId):
        serialized["id"] = str(serialized.pop("_id"))
    return serialized


class EventCreate(BaseModel):
    name: str = Field(..., min_length=1)
    venue: str = Field(..., min_length=1)
    date: str
    description: str | None = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        datetime.fromisoformat(value)
        return value


class EventUpdate(BaseModel):
    name: str | None = None
    venue: str | None = None
    date: str | None = None
    description: str | None = None


class TicketCreate(BaseModel):
    event_id: str
    customer_name: str = Field(..., min_length=1)
    email: str
    ticket_type: str = Field(..., min_length=1)
    price: float = Field(..., ge=0)
    status: str = "active"


class CheckinPayload(BaseModel):
    checked_in_by: str = Field(..., min_length=1)
    notes: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "event-ticket-logger"}


@app.get("/events")
def list_events():
    docs = list(get_collection("events").find({}))
    return [serialize_mongo_doc(doc) for doc in docs]


@app.post("/events", status_code=201)
def create_event(payload: EventCreate):
    event = {
        "name": payload.name,
        "venue": payload.venue,
        "date": payload.date,
        "description": payload.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = get_collection("events").insert_one(event)
    created = get_collection("events").find_one({"_id": result.inserted_id})
    return serialize_mongo_doc(created)


@app.get("/events/{event_id}")
def get_event(event_id: str):
    doc = get_collection("events").find_one({"_id": ObjectId(event_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Event not found")
    return serialize_mongo_doc(doc)


@app.patch("/events/{event_id}")
def update_event(event_id: str, payload: EventUpdate):
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items() if v is not None}
    if not updates:
        return get_event(event_id)
    get_collection("events").update_one({"_id": ObjectId(event_id)}, {"$set": updates})
    doc = get_collection("events").find_one({"_id": ObjectId(event_id)})
    return serialize_mongo_doc(doc)


@app.get("/tickets")
def list_tickets():
    docs = list(get_collection("tickets").find({}))
    return [serialize_mongo_doc(doc) for doc in docs]


@app.post("/tickets", status_code=201)
def create_ticket(payload: TicketCreate):
    event_lookup = get_collection("events").find_one({"_id": ObjectId(payload.event_id)})
    if not event_lookup:
        raise HTTPException(status_code=404, detail="Event not found")

    ticket = {
        "event_id": payload.event_id,
        "customer_name": payload.customer_name,
        "email": payload.email,
        "ticket_type": payload.ticket_type,
        "price": payload.price,
        "status": payload.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checkins": [],
    }
    result = get_collection("tickets").insert_one(ticket)
    created = get_collection("tickets").find_one({"_id": result.inserted_id})
    return serialize_mongo_doc(created)


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    doc = get_collection("tickets").find_one({"_id": ObjectId(ticket_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return serialize_mongo_doc(doc)


@app.post("/tickets/{ticket_id}/checkin")
def check_in(ticket_id: str, payload: CheckinPayload):
    ticket = get_collection("tickets").find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    checkin_entry = {
        "checked_in_by": payload.checked_in_by,
        "notes": payload.notes,
        "checked_in_at": datetime.now(timezone.utc).isoformat(),
    }
    get_collection("tickets").update_one(
        {"_id": ObjectId(ticket_id)},
        {"$set": {"status": "checked-in"}, "$push": {"checkins": checkin_entry}},
    )
    updated = get_collection("tickets").find_one({"_id": ObjectId(ticket_id)})
    return serialize_mongo_doc(updated)
