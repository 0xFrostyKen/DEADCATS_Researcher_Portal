from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.sql import func
from core.database import Base

class Achievement(Base):
    __tablename__ = "achievements"

    id       = Column(Integer, primary_key=True, index=True)
    icon     = Column(String(10), nullable=False)
    name     = Column(String(100), nullable=False, unique=True)
    desc     = Column("desc", String(500), default="")
    rarity   = Column(String(20), default="common")  # legendary|rare|uncommon|common

    def to_dict(self):
        return {
            "id":     self.id,
            "icon":   self.icon,
            "name":   self.name,
            "desc":   self.desc,
            "rarity": self.rarity,
        }

class UserAchievement(Base):
    __tablename__ = "user_achievements"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)
    unlocked       = Column(Boolean, default=True)
    equipped       = Column(Boolean, default=False)
    unlocked_at    = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":             self.id,
            "user_id":        self.user_id,
            "achievement_id": self.achievement_id,
            "unlocked":       self.unlocked,
            "equipped":       self.equipped,
            "unlocked_at":    str(self.unlocked_at),
        }

class UserSpecialization(Base):
    __tablename__ = "user_specializations"

    id      = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    icon    = Column(String(10), default="🔧")
    name    = Column(String(100), nullable=False)
    level   = Column(String(10), default="NOVICE")  # ELITE|ADV|MID|NOVICE

    def to_dict(self):
        return {
            "id":      self.id,
            "user_id": self.user_id,
            "icon":    self.icon,
            "name":    self.name,
            "level":   self.level,
        }
