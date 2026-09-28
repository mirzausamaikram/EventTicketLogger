# Event Ticket Logger

A small FastAPI application for tracking events, ticket sales, ticket scans, and backup records in MongoDB.

## Features

- Event management
- Ticket inventory and sales tracking
- Check-in / scan logging
- Search and backup-friendly JSON API
- MongoDB-backed persistence

## Run locally

1. Start MongoDB locally.
2. Copy `.env.example` to `.env` and adjust values.
3. Install dependencies:
   `python -m pip install -r requirements.txt`
4. Run:
   `uvicorn app.main:app --reload`

## API

- `GET /health`
- `GET /events`
- `POST /events`
- `GET /events/{event_id}`
- `GET /tickets`
- `POST /tickets`
- `GET /tickets/{ticket_id}`
- `POST /tickets/{ticket_id}/checkin`

## Notes

This is meant as a clean starter project for a weekend build and can be expanded with authentication, dashboards, or export features.
