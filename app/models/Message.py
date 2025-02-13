from .meta import DirtyTrackingMeta

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
    latitude: float = None
    longitude: float = None

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)