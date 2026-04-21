from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

class MongoDB:
    _client = None
    _db = None

    @classmethod
    def connect(cls):
        if cls._client is None:
            try:
                MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
                cls._client = MongoClient(MONGO_URI)
                print("✅ MongoDB Connected")
            except Exception as e:
                print("❌ MongoDB Connection Error:", e)
        return cls._client

    @classmethod
    def get_db(cls):
        if cls._db is None:
            client = cls.connect()
            DB_NAME = os.getenv("DB_NAME", "fashionhub")
            cls._db = client[DB_NAME]
        return cls._db

    @classmethod
    def get_collection(cls, name):
        return cls.get_db()[name]