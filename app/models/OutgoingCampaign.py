from .meta import DirtyTrackingMeta


class OutgoingCampaign(metaclass=DirtyTrackingMeta):
    name: str
    audienceName: str
    message: str
    status: str
    transport: str
    scheduledAt: str
    createdAt: str
    createdBy: str
    lastRunAt: str
    lastError: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
