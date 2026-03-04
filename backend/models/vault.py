from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.sql import func
from core.database import Base

class VaultFile(Base):
    __tablename__ = "vault_files"

    id           = Column(Integer, primary_key=True, index=True)
    filename     = Column(String(500), nullable=False)
    original_name= Column(String(500), nullable=False)
    mimetype     = Column(String(200), default="application/octet-stream")
    size         = Column(BigInteger, default=0)
    sha256       = Column(String(64), default="")
    tags         = Column(String(500), default="")
    description  = Column(Text, default="")
    author       = Column(String(50), nullable=False)
    author_id    = Column(Integer, ForeignKey("users.id"))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":            self.id,
            "filename":      self.filename,
            "original_name": self.original_name,
            "mimetype":      self.mimetype,
            "size":          self.size,
            "sha256":        self.sha256,
            "tags":          self.tags.split(",") if self.tags else [],
            "description":   self.description,
            "author":        self.author,
            "author_id":     self.author_id,
            "created_at":    str(self.created_at),
        }

