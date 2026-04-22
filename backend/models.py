import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    age = Column(BigInteger, nullable=True)
    gender = Column(String, nullable=True)
    photo_id = Column(String, nullable=True)
    city = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    preferred_gender = Column(String, nullable=True)
    preferred_city = Column(String, nullable=True)
    preferred_age_min = Column(Integer, nullable=True)
    preferred_age_max = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("from_tg_id", "to_tg_id", name="uq_like"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_tg_id = Column(BigInteger, nullable=False, index=True)
    to_tg_id = Column(BigInteger, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Skip(Base):
    __tablename__ = "skips"
    __table_args__ = (UniqueConstraint("from_tg_id", "to_tg_id", name="uq_skip"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_tg_id = Column(BigInteger, nullable=False, index=True)
    to_tg_id = Column(BigInteger, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("user1_tg_id", "user2_tg_id", name="uq_match_pair"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user1_tg_id = Column(BigInteger, nullable=False, index=True)
    user2_tg_id = Column(BigInteger, nullable=False, index=True)
    dialog_started = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserRating(Base):
    __tablename__ = "user_ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    primary_score = Column(Float, nullable=False, default=0.0)
    behavioral_score = Column(Float, nullable=False, default=0.0)
    combined_score = Column(Float, nullable=False, default=0.0)
    likes_received = Column(Integer, nullable=False, default=0)
    skips_received = Column(Integer, nullable=False, default=0)
    matches_count = Column(Integer, nullable=False, default=0)
    dialogs_started = Column(Integer, nullable=False, default=0)
    last_calculated_at = Column(DateTime, default=datetime.utcnow)