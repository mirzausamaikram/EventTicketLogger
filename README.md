# Event Ticket Logger

A MongoDB-backed incident and ticket tracking API for support operations, service analytics, and live ticket metrics. The project combines event management, ticket handling, dashboard reporting, and authentication in one lightweight application.

## Highlights

- Secure admin login with bearer-token auth
- Ticket and incident collection APIs
- MongoDB aggregation-based reporting for support metrics
- CSV/JSON exports for downstream reporting and backups
- Simple dashboard UI for live support health monitoring
- Docker Compose setup for local MongoDB development

## Tech stack

- Python 3.13+
- FastAPI
- MongoDB
- Pydantic validation
- Pytest

## Local setup

1. Clone the repository.
2. Copy `.env.example` to `.env` and update your local values.
3. Start MongoDB:
   `docker compose up -d`
4. Install dependencies:
   `python -m pip install -r requirements.txt`
5. Run the API:
   `python -m uvicorn app.main:app --reload`

The app will run on `http://127.0.0.1:8000`.

## Default credentials

- Username: `admin`
- Password: `admin123`

> Change these values in your `.env` file before using the project in a real environment.

## Dashboard

Open the dashboard in your browser:

`http://127.0.0.1:8000/`

It includes:

- Login page first; after signing in, the dashboard opens.
- Raise tickets with a title, description, category, priority, and optional owner.
- Move tickets through `open`, `in-progress`, and `resolved` using the status selector and **Save** button.
- Open, in-progress, resolved, and high-priority ticket counts.
- Recent ticket table and support analytics.
- **Logout** returns to the login page.

Use the demo credentials above to try the workflow. Sample tickets are seeded automatically when the ticket collection is empty.

## API overview

### Auth

- `POST /login`
  - Body: `{ "username": "admin", "password": "admin123" }`
  - Returns a bearer token

### Support and ticket endpoints

- `GET /health`
- `GET /incidents`
- `POST /incidents`
- `PATCH /incidents/{incident_id}` with `{ "status": "in-progress" }` or `{ "status": "resolved" }`
- `GET /tickets`
- `POST /tickets`
- `GET /tickets/{ticket_id}`
- `POST /tickets/{ticket_id}/checkin`
- `GET /events`
- `POST /events`
- `GET /events/{event_id}`

### Reporting and export

- `GET /reports/summary`
  - Requires `Authorization: Bearer <token>`
  - Returns total, open, in-progress, resolved, and escalated ticket counts
  - Includes status, priority, and category aggregation data
- `GET /incidents`, `POST /incidents`, and `PATCH /incidents/{incident_id}` require `Authorization: Bearer <token>`.
- `GET /reports/export?format=json`
- `GET /reports/export?format=csv`

## Example reporting payload

```json
{
  "total_tickets": 42,
  "open_tickets": 17,
  "resolved_tickets": 21,
  "escalated_tickets": 6,
  "status_breakdown": [
    { "_id": "open", "count": 17 },
    { "_id": "resolved", "count": 21 }
  ]
}
```

## Development notes

This project is intentionally lightweight so it can be built quickly for a weekend demo or proof-of-concept. It is structured to be extended with:

- RBAC and user accounts
- MongoDB indexing
- integration with email or Slack alerts
- report charts and PDF exports
- production-grade deployment with Docker or Azure

## License

This project is provided as a starter application for internal demos and learning. Update the license if you plan to publish or distribute it publicly.
