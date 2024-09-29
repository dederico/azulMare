from .meta import DirtyTrackingMeta

class Config(metaclass=DirtyTrackingMeta):
    name: str
    value: str

    def getval(self):
        if self.value.lower() in ['none', 'null']:
            return None

        if self.value.lower() in ['true', 'false']:
            return self.value.lower() == 'true'

        try:
            return int(self.value)
        except ValueError:
            pass

        try:
            return float(self.value)
        except ValueError:
            pass

        return self.value

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)