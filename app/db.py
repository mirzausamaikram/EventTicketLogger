from pymongo import MongoClient

from app.config import MONGODB_DB, MONGODB_URI

client = MongoClient(MONGODB_URI)
db = client[MONGODB_DB]


def get_collection(name: str):
    return db[name]
