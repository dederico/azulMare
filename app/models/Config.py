from .meta import DirtyTrackingMeta

class Config(metaclass=DirtyTrackingMeta):
    name: str
    value: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)