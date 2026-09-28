from __future__ import annotations

from copy import deepcopy

from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config import MONGODB_DB, MONGODB_URI


class MemoryCollection:
    def __init__(self, name: str):
        self.name = name
        self._docs = []

    def _normalize(self, doc: dict):
        if "_id" not in doc:
            doc = {"_id": ObjectId(), **doc}
        return deepcopy(doc)

    def find(self, query=None):
        query = query or {}
        return [deepcopy(doc) for doc in self._docs if all(doc.get(key) == value for key, value in query.items())]

    def find_one(self, query):
        q = query or {}
        for doc in self._docs:
            if all(doc.get(key) == value for key, value in q.items()):
                return deepcopy(doc)
        return None

    def insert_one(self, document):
        doc = self._normalize(document)
        self._docs.append(doc)
        return type("Result", (), {"inserted_id": doc["_id"]})()

    def update_one(self, query, update):
        for doc in self._docs:
            if all(doc.get(key) == value for key, value in query.items()):
                if "$set" in update:
                    doc.update(update["$set"])
                if "$push" in update:
                    for key, value in update["$push"].items():
                        doc.setdefault(key, []).append(value)
                return None
        return None

    def aggregate(self, pipeline):
        results = []
        for stage in pipeline:
            if "$group" in stage:
                key = stage["$group"]["_id"]
                if isinstance(key, str) and key.startswith("$"):
                    field = key[1:]
                    groups = {}
                    for doc in self._docs:
                        groups.setdefault(doc.get(field), 0)
                        groups[doc.get(field)] += 1
                    results = [{"_id": group, "count": count} for group, count in groups.items()]
                break
        return results


class MemoryDatabase:
    def __init__(self):
        self._collections = {}

    def __getitem__(self, name: str):
        if name not in self._collections:
            self._collections[name] = MemoryCollection(name)
        return self._collections[name]


class SafeCollection:
    def __init__(self, name: str):
        self.name = name
        self.memory = MemoryCollection(name)
        self.mongo = None
        self.mongo_available = False

        try:
            client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=1500)
            client.admin.command("ping")
            self.mongo = client[MONGODB_DB][name]
            self.mongo_available = True
        except (PyMongoError, Exception):
            self.mongo_available = False

    def _call(self, func_name, *args, **kwargs):
        if self.mongo_available and self.mongo is not None:
            try:
                return getattr(self.mongo, func_name)(*args, **kwargs)
            except (PyMongoError, Exception):
                self.mongo_available = False
        return getattr(self.memory, func_name)(*args, **kwargs)

    def find(self, query=None):
        return self._call("find", query)

    def find_one(self, query):
        return self._call("find_one", query)

    def insert_one(self, document):
        return self._call("insert_one", document)

    def update_one(self, query, update):
        return self._call("update_one", query, update)

    def aggregate(self, pipeline):
        return self._call("aggregate", pipeline)


memory_db = MemoryDatabase()
_collections = {}


def get_collection(name: str):
    if name not in _collections:
        _collections[name] = SafeCollection(name)
    return _collections[name]
