from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from core.database import Base


class TeamGoal(Base):
    __tablename__ = "team_goals"

    id           = Column(Integer, primary_key=True, index=True)
    text         = Column(String(500), nullable=False)
    completed    = Column(Boolean, default=False, nullable=False)
    created_by   = Column(String(50), nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(String(50), nullable=True)

    def to_dict(self):
        return {
            "id":           self.id,
            "text":         self.text,
            "completed":    self.completed,
            "created_by":   self.created_by,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "completed_by": self.completed_by,
        }
