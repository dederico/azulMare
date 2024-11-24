from .meta import DirtyTrackingMeta
from pydantic import BaseModel

class MessageResponseSenders(BaseModel):
    senderName: str
    number: str
    time: str

class MessageResponse(BaseModel):
    senderName: str
    source: str
    number: str
    mtype: str
    direction: str
    time: str
    uid: str
    url: str
    message: str

    class Config:
        from_attributes = True

class Message(metaclass=DirtyTrackingMeta):
    senderName: str
    source: str
    number: str
    mtype: str
    direction: str
    time: str
    uid: str
    url: str
    message: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)