class Notification:
    nType: str
    nCategory: str
    nTitle: str
    nBody: str
    nTime: str
    nAck: bool

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)