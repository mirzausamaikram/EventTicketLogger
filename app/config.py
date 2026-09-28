import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "ticket_logger")
APP_NAME = os.getenv("APP_NAME", "Event Ticket Logger")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "event-ticket-logger-dev-secret")
DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "admin123")
