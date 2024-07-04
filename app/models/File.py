from .meta import DirtyTrackingMeta

class File(metaclass=DirtyTrackingMeta):
    name: str
    data: bytes

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)