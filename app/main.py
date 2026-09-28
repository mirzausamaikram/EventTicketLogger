import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.config import APP_SECRET_KEY, DEFAULT_PASSWORD, DEFAULT_USERNAME
from app.db import get_collection

app = FastAPI(title="Event Ticket Logger", version="1.0.0")


def serialize_mongo_doc(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    serialized = dict(doc)
    if "_id" in serialized and isinstance(serialized["_id"], ObjectId):
        serialized["id"] = str(serialized.pop("_id"))
    return serialized


def b64_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("utf-8")


def b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "role": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400,
    }
    header = b64_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = b64_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode()
    signature = hmac.new(APP_SECRET_KEY.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{b64_encode(signature)}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        header, body, signature = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token format") from exc

    expected = b64_encode(
        hmac.new(APP_SECRET_KEY.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Token signature mismatch")

    payload = json.loads(b64_decode(body).decode("utf-8"))
    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired")
    return payload


def require_auth(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.split(" ", 1)[1]
    return decode_token(token)


def count_records(collection: Any, query: dict[str, Any] | None = None) -> int:
    query = query or {}
    if hasattr(collection, "count_documents"):
        return collection.count_documents(query)
    records = list(collection.find({}))
    if not query:
        return len(records)
    count = 0
    for record in records:
        if "status" in query and isinstance(query["status"], dict) and "$in" in query["status"]:
            if record.get("status") in query["status"]["$in"]:
                count += 1
        elif all(record.get(key) == value for key, value in query.items()):
            count += 1
    return count


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


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


class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=1)
    status: Literal["open", "in-progress", "resolved"] = "open"
    priority: str = "medium"
    category: str = "general"
    description: str | None = None
    owner: str | None = None
    created_at: str | None = None


class IncidentStatusUpdate(BaseModel):
    status: Literal["open", "in-progress", "resolved"]


class CheckinPayload(BaseModel):
    checked_in_by: str = Field(..., min_length=1)
    notes: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "event-ticket-logger"}


@app.post("/login")
def login(payload: LoginRequest):
    if payload.username == DEFAULT_USERNAME and payload.password == DEFAULT_PASSWORD:
        return {"token": create_token(payload.username), "user": payload.username}
    raise HTTPException(status_code=401, detail="Invalid credentials")


def seed_demo_data():
        ticket_collection = get_collection("tickets")
        if hasattr(ticket_collection, "find") and list(ticket_collection.find({})):
                return

        demo_tickets = [
                {
                        "title": "Login failure after password reset",
                        "status": "open",
                        "priority": "high",
                        "category": "access",
                        "owner": "support-team",
                        "description": "Users are unable to complete the SSO challenge after reset.",
                        "created_at": "2026-09-28T08:30:00Z",
                },
                {
                        "title": "Invoice sync delay",
                        "status": "resolved",
                        "priority": "medium",
                        "category": "billing",
                        "owner": "finance-ops",
                        "description": "Late nightly sync queue for invoice posting.",
                        "created_at": "2026-09-27T16:15:00Z",
                },
                {
                        "title": "API timeout for event imports",
                        "status": "in-progress",
                        "priority": "high",
                        "category": "platform",
                        "owner": "engineering",
                        "description": "PowerBI export endpoint occasionally times out during peak hours.",
                        "created_at": "2026-09-28T09:45:00Z",
                },
        ]
        for ticket in demo_tickets:
                ticket_collection.insert_one(ticket)


@app.get("/", response_class=HTMLResponse)
def login_page():
        return HTMLResponse(
                """
                <!doctype html>
                <html lang="en">
                <head>
                    <meta charset="utf-8" />
                    <meta name="viewport" content="width=device-width, initial-scale=1" />
                    <title>Event Ticket Logger Login</title>
                    <style>
                        body { font-family: Arial, sans-serif; margin: 0; background: #f4f7fb; color: #1f2937; }
                        .login-shell { min-height: 100vh; display: grid; place-items: center; }
                        .panel { width: min(420px, 90vw); background: white; border-radius: 18px; padding: 32px; box-shadow: 0 14px 40px rgba(15, 23, 42, 0.12); }
                        h1 { margin-top: 0; }
                        .muted { color: #64748b; margin: 8px 0 20px; }
                        label { display: block; font-weight: 600; margin-bottom: 8px; }
                        input { width: 100%; box-sizing: border-box; margin-bottom: 16px; padding: 12px; border-radius: 10px; border: 1px solid #dbe3ef; font-size: 14px; }
                        button { width: 100%; padding: 12px 16px; border-radius: 10px; border: none; background: #2563eb; color: white; font-size: 16px; cursor: pointer; }
                        .hint { margin-top: 12px; font-size: 13px; color: #475569; }
                    </style>
                </head>
                <body>
                    <div class="login-shell">
                        <div class="panel">
                            <h1>Event Ticket Logger</h1>
                            <p class="muted">Sign in to view incidents, analytics, and ticket reports.</p>
                            <label for="username">Username</label>
                            <input id="username" value="admin" />
                            <label for="password">Password</label>
                            <input id="password" type="password" value="admin123" />
                            <button onclick="loginUser()">Login</button>
                            <div class="hint">Demo access: admin / admin123</div>
                        </div>
                    </div>
                    <script>
                        async function loginUser() {
                            const username = document.getElementById('username').value;
                            const password = document.getElementById('password').value;
                            const response = await fetch('/login', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ username, password })
                            });
                            const data = await response.json();
                            if (!response.ok) {
                                alert(data.detail || 'Login failed');
                                return;
                            }
                            localStorage.setItem('ticket_logger_token', data.token);
                            window.location.href = '/dashboard';
                        }
                    </script>
                </body>
                </html>
                """
        )


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
        seed_demo_data()
        return HTMLResponse(
                """
                <!doctype html>
                <html lang="en">
                <head>
                    <meta charset="utf-8" />
                    <meta name="viewport" content="width=device-width, initial-scale=1" />
                    <title>Event Ticket Logger Dashboard</title>
                    <style>
                        body { font-family: Arial, sans-serif; background: #f4f7fb; margin: 0; padding: 24px; color: #1f2937; }
                        .container { max-width: 1100px; margin: 0 auto; }
                        .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
                        .panel { background: white; border-radius: 16px; padding: 24px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); margin-bottom: 24px; }
                        .row { display: flex; gap: 16px; flex-wrap: wrap; }
                        .card { background: linear-gradient(135deg, #0f172a, #1d4ed8); color: white; border-radius: 16px; padding: 20px; min-width: 180px; flex: 1; }
                        .muted { color: #64748b; }
                        button { padding: 10px 14px; border-radius: 10px; border: none; cursor: pointer; }
                        .primary { background: #2563eb; color: white; }
                        .secondary { background: #e2e8f0; color: #0f172a; }
                        input, textarea, select { box-sizing: border-box; width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font: inherit; }
                        .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin: 16px 0; }
                        .form-grid label { display: grid; gap: 6px; font-weight: 600; }
                        .wide { grid-column: 1 / -1; }
                        .ticket-title { font-weight: 700; }
                        .ticket-description { margin-top: 5px; max-width: 420px; color: #64748b; white-space: pre-wrap; }
                        .status-control { display: flex; min-width: 210px; gap: 8px; align-items: center; }
                        .status-control select { min-width: 125px; }
                        .status-control button { background: #0f766e; color: white; }
                        .notice { min-height: 20px; margin: 0 0 12px; color: #0f766e; }
                        table { width: 100%; border-collapse: collapse; margin-top: 12px; }
                        th, td { padding: 10px 12px; border-bottom: 1px solid #e5e7eb; text-align: left; }
                        .empty { color: #64748b; font-style: italic; }
                        @media (max-width: 640px) { body { padding: 12px; } .form-grid { grid-template-columns: 1fr; } .wide { grid-column: auto; } .topbar { gap: 12px; } }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="topbar panel">
                            <div>
                                <h1 style="margin:0;">Event Ticket Logger</h1>
                                <div class="muted">Support analytics and incident dashboard</div>
                            </div>
                            <button class="secondary" onclick="logoutUser()">Logout</button>
                        </div>

                        <div id="dashboardContent">
                            <div id="metrics" class="row"></div>
                            <div class="panel">
                                <h2>Raise a ticket</h2>
                                <div id="ticketMessage" class="notice" role="status"></div>
                                <form id="ticketForm" onsubmit="createIncident(event)">
                                    <div class="form-grid">
                                        <label>Issue title<input name="title" required maxlength="160" placeholder="What went wrong?"></label>
                                        <label>Category<input name="category" required maxlength="80" placeholder="For example, access or billing"></label>
                                        <label>Priority
                                            <select name="priority">
                                                <option value="low">Low</option>
                                                <option value="medium" selected>Medium</option>
                                                <option value="high">High</option>
                                            </select>
                                        </label>
                                        <label>Owner<input name="owner" maxlength="80" placeholder="Team or person"></label>
                                        <label class="wide">Description<textarea name="description" rows="3" placeholder="Add details that will help investigate and resolve this ticket"></textarea></label>
                                    </div>
                                    <button class="primary" type="submit">Create ticket</button>
                                </form>
                            </div>
                            <div class="panel">
                                <h2>Recent tickets</h2>
                                <div style="overflow-x:auto;">
                                    <table>
                                        <thead>
                                            <tr><th>Ticket</th><th>Category</th><th>Priority</th><th>Owner</th><th>Status</th></tr>
                                        </thead>
                                        <tbody id="ticketTable"></tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                    <script>
                        const token = localStorage.getItem('ticket_logger_token');
                        if (!token) {
                            window.location.href = '/';
                        }

                        async function loadSummary() {
                            const response = await fetch('/reports/summary', {
                                headers: { Authorization: 'Bearer ' + token }
                            });
                            const data = await response.json();
                            if (!response.ok) {
                                alert(data.detail || 'Access denied');
                                localStorage.removeItem('ticket_logger_token');
                                window.location.href = '/';
                                return;
                            }

                            document.getElementById('metrics').innerHTML = `
                                <div class="card"><h3>Total</h3><h2>${data.total_tickets}</h2></div>
                                <div class="card"><h3>Open</h3><h2>${data.open_tickets}</h2></div>
                                <div class="card"><h3>In progress</h3><h2>${data.in_progress_tickets}</h2></div>
                                <div class="card"><h3>Resolved</h3><h2>${data.resolved_tickets}</h2></div>
                                <div class="card"><h3>Escalated</h3><h2>${data.escalated_tickets}</h2></div>
                            `;

                            if ((data.ticket_rows || []).length === 0) {
                                document.getElementById('ticketTable').innerHTML = '<tr><td colspan="5" class="empty">No tickets yet.</td></tr>';
                                return;
                            }

                            const statuses = ['open', 'in-progress', 'resolved'];
                            document.getElementById('ticketTable').innerHTML = data.ticket_rows.map(ticket => {
                                const ticketId = escapeHtml(ticket.id);
                                const status = statuses.includes(ticket.status) ? ticket.status : 'open';
                                const statusOptions = statuses.map(option => `
                                    <option value="${option}" ${status === option ? 'selected' : ''}>${option.replace('-', ' ')}</option>
                                `).join('');
                                return `
                                    <tr>
                                        <td><div class="ticket-title">${escapeHtml(ticket.title || 'Untitled ticket')}</div><div class="ticket-description">${escapeHtml(ticket.description || '')}</div></td>
                                        <td>${escapeHtml(ticket.category)}</td>
                                        <td>${escapeHtml(ticket.priority)}</td>
                                        <td>${escapeHtml(ticket.owner || 'Unassigned')}</td>
                                        <td><div class="status-control"><select id="status-${ticketId}" aria-label="Status for ${ticketId}">${statusOptions}</select><button type="button" onclick="saveStatus('${ticketId}')">Save</button></div></td>
                                    </tr>
                                `;
                            }).join('');
                        }

                        function escapeHtml(value) {
                            return String(value ?? '').replace(/[&<>"']/g, character => ({
                                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
                            })[character]);
                        }

                        function showTicketMessage(message, isError = false) {
                            const element = document.getElementById('ticketMessage');
                            element.textContent = message;
                            element.style.color = isError ? '#b91c1c' : '#0f766e';
                        }

                        async function createIncident(event) {
                            event.preventDefault();
                            const form = event.currentTarget;
                            const values = Object.fromEntries(new FormData(form).entries());
                            const response = await fetch('/incidents', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
                                body: JSON.stringify({
                                    title: values.title,
                                    category: values.category,
                                    priority: values.priority,
                                    owner: values.owner || null,
                                    description: values.description || null
                                })
                            });
                            const data = await response.json();
                            if (!response.ok) {
                                showTicketMessage(data.detail || 'Could not create ticket.', true);
                                return;
                            }
                            form.reset();
                            showTicketMessage('Ticket created. Assign an owner and update its status as work progresses.');
                            await loadSummary();
                        }

                        async function saveStatus(ticketId) {
                            const status = document.getElementById('status-' + ticketId).value;
                            const response = await fetch('/incidents/' + ticketId, {
                                method: 'PATCH',
                                headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
                                body: JSON.stringify({ status })
                            });
                            const data = await response.json();
                            if (!response.ok) {
                                showTicketMessage(data.detail || 'Could not update ticket status.', true);
                                return;
                            }
                            showTicketMessage('Ticket status updated to ' + data.status.replace('-', ' ') + '.');
                            await loadSummary();
                        }

                        function logoutUser() {
                            localStorage.removeItem('ticket_logger_token');
                            window.location.href = '/';
                        }

                        loadSummary();
                    </script>
                </body>
                </html>
                """
        )


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


@app.get("/incidents")
def list_incidents(user: dict[str, Any] = Depends(require_auth)):
    docs = list(get_collection("tickets").find({}))
    return [serialize_mongo_doc(doc) for doc in docs]


@app.post("/incidents", status_code=201)
def create_incident(payload: IncidentCreate, user: dict[str, Any] = Depends(require_auth)):
    incident = {
        "title": payload.title,
        "status": payload.status,
        "priority": payload.priority,
        "category": payload.category,
        "description": payload.description,
        "owner": payload.owner,
        "created_at": payload.created_at or datetime.now(timezone.utc).isoformat(),
    }
    result = get_collection("tickets").insert_one(incident)
    created = get_collection("tickets").find_one({"_id": result.inserted_id})
    return serialize_mongo_doc(created)


@app.patch("/incidents/{incident_id}")
def update_incident_status(
    incident_id: str,
    payload: IncidentStatusUpdate,
    user: dict[str, Any] = Depends(require_auth),
):
    try:
        object_id = ObjectId(incident_id)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="Invalid ticket ID") from exc

    collection = get_collection("tickets")
    if not collection.find_one({"_id": object_id}):
        raise HTTPException(status_code=404, detail="Ticket not found")

    collection.update_one(
        {"_id": object_id},
        {"$set": {"status": payload.status, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    updated = collection.find_one({"_id": object_id})
    return serialize_mongo_doc(updated)


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


@app.get("/reports/summary")
def ticket_summary(user: dict[str, Any] = Depends(require_auth)):
    collection = get_collection("tickets")

    tickets = list(collection.find({}))
    total_tickets = len(tickets)
    open_tickets = sum(1 for doc in tickets if str(doc.get("status", "")).lower() in {"open", "new", "active"})
    in_progress_tickets = sum(1 for doc in tickets if str(doc.get("status", "")).lower() == "in-progress")
    resolved_tickets = sum(1 for doc in tickets if str(doc.get("status", "")).lower() == "resolved")
    escalated_tickets = sum(1 for doc in tickets if str(doc.get("priority", "")).lower() == "high")

    status_breakdown = list(collection.aggregate([{"$group": {"_id": "$status", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]))
    priority_breakdown = list(collection.aggregate([{"$group": {"_id": "$priority", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]))
    category_breakdown = list(collection.aggregate([{"$group": {"_id": "$category", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]))

    return {
        "user": user.get("sub"),
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "in_progress_tickets": in_progress_tickets,
        "resolved_tickets": resolved_tickets,
        "escalated_tickets": escalated_tickets,
        "status_breakdown": status_breakdown,
        "priority_breakdown": priority_breakdown,
        "category_breakdown": category_breakdown,
        "ticket_rows": [
            {
                "id": str(doc.get("_id", "")),
                "title": doc.get("title") or doc.get("customer_name") or "Untitled ticket",
                "status": doc.get("status", "open"),
                "priority": doc.get("priority", "medium"),
                "category": doc.get("category") or doc.get("ticket_type") or "general",
                "owner": doc.get("owner"),
                "description": doc.get("description"),
            }
            for doc in tickets[:10]
        ],
    }


@app.get("/reports/export")
def export_report(format: str = Query(default="json", pattern="^(json|csv)$"), user: dict[str, Any] = Depends(require_auth)):
    collection = get_collection("tickets")
    tickets = list(collection.find({}))

    if format == "csv":
        headers = ["title", "status", "priority", "category", "owner", "created_at"]
        rows = [
            [
                doc.get("title") or doc.get("customer_name") or "",
                doc.get("status", ""),
                doc.get("priority", ""),
                doc.get("category") or doc.get("ticket_type") or "",
                doc.get("owner") or "",
                doc.get("created_at") or "",
            ]
            for doc in tickets
        ]
        csv_lines = [",".join(headers)] + [",".join(str(value) for value in row) for row in rows]
        return JSONResponse(content={"format": "csv", "rows": csv_lines})

    return {
        "user": user.get("sub"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tickets": [serialize_mongo_doc(doc) for doc in tickets],
    }
