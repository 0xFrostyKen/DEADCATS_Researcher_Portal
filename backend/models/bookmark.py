from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from core.database import Base


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "item_type", "item_id", name="uq_bookmark"),
    )

    id        = Column(Integer, primary_key=True, index=True)
    user_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item_type = Column(String(10), nullable=False)   # "note" or "ioc"
    item_id   = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":         self.id,
            "user_id":    self.user_id,
            "item_type":  self.item_type,
            "item_id":    self.item_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
