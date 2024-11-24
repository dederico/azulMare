from .meta import DirtyTrackingMeta
from pydantic import BaseModel

class NotificationResponse(BaseModel):
    nType: str
    nCategory: str
    nTitle: str
    nBody: str
    nTime: str
    nAck: bool

    class Config:
        from_attributes = True

class Notification(metaclass=DirtyTrackingMeta):
    nType: str
    nCategory: str
    nTitle: str
    nBody: str
    nTime: str
    nAck: bool

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)