from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from core.database import Base

# Rank choices — stored as string
# DEADCAT | Scholar | Lead Researcher | Founding Circle
RANKS = ["DEADCAT", "Scholar", "Lead Researcher", "Founding Circle"]

class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, index=True)
    handle     = Column(String(50), unique=True, index=True, nullable=False)
    password   = Column(String(255), nullable=False)
    bio        = Column(Text, default="")
    emoji      = Column(String(10), default="🐱")
    rank       = Column(String(20), default="DEADCAT")
    is_admin   = Column(Boolean, default=False)
    is_active  = Column(Boolean, default=True)

    # Social links
    avatar_url = Column(String(500), default="")
    banner_url = Column(String(500), default="")
    title      = Column(String(100), default="")    
    github     = Column(String(100), default="")
    twitter    = Column(String(100), default="")
    htb        = Column(String(100), default="")
    ctftime    = Column(String(100), default="")
    profile_status = Column(String(40), default="available")

    # Stats — updated by other modules later
    notes_count    = Column(Integer, default=0)
    iocs_count     = Column(Integer, default=0)
    files_count    = Column(Integer, default=0)
    findings_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen  = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self, include_private=False):
        data = {
            "id":            self.id,
            "handle":        self.handle,
            "bio":           self.bio,
            "emoji":         self.emoji,
            "rank":          self.rank,
            "is_admin":      self.is_admin,
            "github":        self.github,
            "twitter":       self.twitter,
            "htb":           self.htb,
            "ctftime":       self.ctftime,
            "profile_status": self.profile_status or "available",
            "stats": {
                "notes":    self.notes_count,
                "iocs":     self.iocs_count,
                "files":    self.files_count,
                "findings": self.findings_count,
            },
            "created_at": str(self.created_at) if self.created_at else None,
            "last_seen":  str(self.last_seen)  if self.last_seen  else None,
            "avatar_url":    self.avatar_url  or "",
            "banner_url":    self.banner_url  or "",
            "title":         self.title       or "",
        }
        if include_private:
            data["is_active"] = self.is_active
        return data
