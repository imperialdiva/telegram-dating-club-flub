import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from sqlalchemy import Column, String, DateTime, BigInteger, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")


engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

app = FastAPI(title="Club Flub Backend")

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
async def health_check():
    return {"status": "ok", "database": "connected"}

@app.post("/register")
async def register_user(tg_id: int, username: Optional[str] = None):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        existing_user = result.scalar_one_or_none()
        if existing_user:
            return {"status": "already_exists", "message": "User already in database"} 
        try:
            new_user = User(telegram_id=tg_id, username=username)
            session.add(new_user)
            await session.commit()
            return {"status": "success", "message": "User registered"}
        except Exception as e:
            await session.rollback()
            return {"status": "error", "message": str(e)} 