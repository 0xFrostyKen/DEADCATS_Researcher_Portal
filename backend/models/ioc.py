from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class IOC(Base):
    __tablename__ = "iocs"

    id           = Column(Integer, primary_key=True, index=True)
    type         = Column(String(20), nullable=False)   # ip|domain|hash|url|email|cve
    value        = Column(String(1000), nullable=False)
    tags         = Column(String(500), default="")
    severity     = Column(String(10), default="medium") # low|medium|high|critical
    notes        = Column(Text, default="")
    author       = Column(String(50), nullable=False)
    author_id    = Column(Integer, ForeignKey("users.id"))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":         self.id,
            "type":       self.type,
            "value":      self.value,
            "tags":       self.tags.split(",") if self.tags else [],
            "severity":   self.severity,
            "notes":      self.notes,
            "author":     self.author,
            "author_id":  self.author_id,
            "created_at": str(self.created_at),
        }

