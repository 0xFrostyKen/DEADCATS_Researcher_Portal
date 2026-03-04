from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class Announcement(Base):
    __tablename__ = "announcements"

    id         = Column(Integer, primary_key=True, index=True)
    title      = Column(String(200), nullable=False)
    content    = Column(Text, default="")
    type       = Column(String(20), default="notice")  # notice | creds
    author     = Column(String(50), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    pinned     = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":         self.id,
            "title":      self.title,
            "content":    self.content,
            "type":       self.type,
            "author":     self.author,
            "pinned":     self.pinned,
            "expires_at": str(self.expires_at) if self.expires_at else None,
            "created_at": str(self.created_at),
        }
