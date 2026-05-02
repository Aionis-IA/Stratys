"""Modèles SQLAlchemy."""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_subscribed = Column(Boolean, default=False, nullable=False)
    user_type = Column(String(32), default="standard", nullable=False)
    company_name = Column(String(255), default="", nullable=False)
    sector = Column(String(255), default="", nullable=False)


class DiagnosticHistory(Base):
    __tablename__ = "diagnostic_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user_type = Column(String(32), nullable=False)
    score = Column(Integer, nullable=False)
    summary = Column(Text, default="", nullable=False)
    strength = Column(Text, default="", nullable=False)
    weakness = Column(Text, default="", nullable=False)
    issues = Column(JSON, nullable=False)
    issues_titles = Column(JSON, nullable=True)
    issues_resolved = Column(JSON, nullable=True)
    result_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
