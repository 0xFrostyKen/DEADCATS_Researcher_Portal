from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class Folder(Base):
    __tablename__ = "folders"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    parent_id  = Column(Integer, ForeignKey("folders.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":         self.id,
            "name":       self.name,
            "parent_id":  self.parent_id,
            "created_by": self.created_by,
            "created_at": str(self.created_at),
        }

class Note(Base):
    __tablename__ = "notes"

    id           = Column(Integer, primary_key=True, index=True)
    title        = Column(String(200), nullable=False)
    content      = Column(Text, default="")
    folder_id    = Column(Integer, ForeignKey("folders.id"), nullable=True)
    author_id    = Column(Integer, ForeignKey("users.id"))
    author_handle= Column(String(50))
    tags         = Column(String(500), default="")   # comma separated
    published    = Column(Boolean, default=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id":            self.id,
            "title":         self.title,
            "content":       self.content,
            "folder_id":     self.folder_id,
            "author_id":     self.author_id,
            "author_handle": self.author_handle,
            "tags":          self.tags.split(",") if self.tags else [],
            "published":     self.published,
            "created_at":    str(self.created_at),
            "updated_at":    str(self.updated_at) if self.updated_at else None,
        }
