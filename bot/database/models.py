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
    total_karma: Mapped[int] = mapped_column(Integer, default=0)
    
    karma_records = relationship("KarmaRecord", back_populates="user")

class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class KarmaRecord(Base):
    __tablename__ = "karma_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"))
    emoji: Mapped[str] = mapped_column(String(10))
    amount: Mapped[int] = mapped_column(Integer) # Can be negative for un-reactions
    message_id: Mapped[int] = mapped_column(BigInteger) # Track which message was reacted to
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="karma_records")
    
    __table_args__ = (
        Index('idx_karma_user_chat', 'user_id', 'chat_id'),
        Index('idx_karma_message', 'message_id'),
    )