from sqlalchemy import Column, Integer, String
from core.database import Base


class WhiteboardConfig(Base):
    __tablename__ = "whiteboard_config"

    id       = Column(Integer, primary_key=True)   # always 1
    room_url = Column(String(500), nullable=False)
