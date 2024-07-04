from .meta import DirtyTrackingMeta

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
    callLogs: str
    callTime: str
    callUid: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)