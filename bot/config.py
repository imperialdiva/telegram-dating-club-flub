import os

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
    BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

config = Config()