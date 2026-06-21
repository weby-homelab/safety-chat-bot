from sqlalchemy import BigInteger, String, Boolean, ForeignKey, Integer, DateTime, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))


class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class BannedDomain(Base):
    __tablename__ = "banned_domains"
    domain: Mapped[str] = mapped_column(String(128), primary_key=True)

class BannedKeyword(Base):
    __tablename__ = "banned_keywords"
    keyword: Mapped[str] = mapped_column(String(128), primary_key=True)