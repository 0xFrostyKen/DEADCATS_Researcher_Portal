from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.sql import func
from core.database import Base


class CTFEvent(Base):
    __tablename__ = "ctf_events"

    id                = Column(Integer, primary_key=True, index=True)
    ctftime_event_id  = Column(Integer, nullable=True)
    title             = Column(String(300), nullable=False)
    url               = Column(String(500), nullable=True)
    start_time        = Column(DateTime(timezone=True), nullable=True)
    end_time          = Column(DateTime(timezone=True), nullable=True)
    format            = Column(String(50), nullable=True)
    weight            = Column(Float, nullable=True)
    description       = Column(Text, nullable=True)
    status            = Column(String(20), nullable=False, default="upcoming")  # upcoming | completed
    added_by          = Column(String(50), nullable=False)
    created_at        = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":               self.id,
            "ctftime_event_id": self.ctftime_event_id,
            "title":            self.title,
            "url":              self.url,
            "start_time":       self.start_time.isoformat() if self.start_time else None,
            "end_time":         self.end_time.isoformat()   if self.end_time   else None,
            "format":           self.format,
            "weight":           self.weight,
            "description":      self.description,
            "status":           self.status,
            "added_by":         self.added_by,
            "created_at":       self.created_at.isoformat() if self.created_at else None,
        }


class CTFResult(Base):
    __tablename__  = "ctf_results"
    __table_args__ = (UniqueConstraint("event_id", name="uq_ctf_result_event"),)

    id            = Column(Integer, primary_key=True, index=True)
    event_id      = Column(Integer, ForeignKey("ctf_events.id"), nullable=False)
    place         = Column(Integer, nullable=False)
    ctf_points    = Column(Float, nullable=False, default=0.0)
    rating_points = Column(Float, nullable=False, default=0.0)
    added_by      = Column(String(50), nullable=False)
    added_at      = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id":            self.id,
            "event_id":      self.event_id,
            "place":         self.place,
            "ctf_points":    self.ctf_points,
            "rating_points": self.rating_points,
            "added_by":      self.added_by,
            "added_at":      self.added_at.isoformat() if self.added_at else None,
        }


class CTFParticipant(Base):
    __tablename__ = "ctf_participants"

    id            = Column(Integer, primary_key=True, index=True)
    event_id      = Column(Integer, ForeignKey("ctf_events.id"), nullable=False)
    member_handle = Column(String(50), nullable=False)
    points        = Column(Float, nullable=False, default=0.0)
    notes         = Column(String(300), nullable=True)
    added_by      = Column(String(50), nullable=False)

    def to_dict(self):
        return {
            "id":            self.id,
            "event_id":      self.event_id,
            "member_handle": self.member_handle,
            "points":        self.points,
            "notes":         self.notes,
            "added_by":      self.added_by,
        }


class CTFParticipationMarker(Base):
    __tablename__  = "ctf_participation_markers"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_ctf_participation_event_user"),)

    id         = Column(Integer, primary_key=True, index=True)
    event_id   = Column(Integer, ForeignKey("ctf_events.id"), nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    handle     = Column(String(50), nullable=False)
    will_play  = Column(Integer, nullable=False, default=1)  # 1=yes, 0=no
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def to_dict(self):
        return {
            "id":         self.id,
            "event_id":   self.event_id,
            "user_id":    self.user_id,
            "handle":     self.handle,
            "will_play":  bool(self.will_play),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
