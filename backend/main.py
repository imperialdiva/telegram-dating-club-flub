from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# Временное хранилище (потом заменим на PostgreSQL из твоего плана)
users_db = {}

class UserCreate(BaseModel):
    telegram_id: int
    username: str | None = None

@app.post("/users/register")
async def register_user(user: UserCreate):
    if user.telegram_id in users_db:
        return {"status": "exists", "message": "User already registered"}
    
    users_db[user.telegram_id] = user
    print(f"Зарегистрирован новый пользователь: {user.telegram_id}")
    return {"status": "success", "user_id": user.telegram_id}