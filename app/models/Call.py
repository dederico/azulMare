from .meta import DirtyTrackingMeta
from pydantic import BaseModel

class ScriptResponse(BaseModel):
    role: str
    dialog: str

    class Config:
        from_attributes = True

class CallResponse(BaseModel):
    id: int
    callUid: str
    callerName: str
    callNumber: str
    callStatus: str
    callDirection: str
    callDuration: int
    callTime: str

    class Config:
        from_attributes = True

class Call(metaclass=DirtyTrackingMeta):
    callerName: str
    callerAddress: str
    callSource: str
    callNumber: str
    callStatus: str
    callType: str
    callDirection: str
    callDuration: int
    callScript: str
    callPlayback: str
    callLogs: str
    callTime: str
    callUid: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)