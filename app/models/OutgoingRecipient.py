from .meta import DirtyTrackingMeta


class OutgoingRecipient(metaclass=DirtyTrackingMeta):
    campaign_id: int
    name: str
    phone: str
    status: str
    sentAt: str
    lastAttemptAt: str
    errorType: str
    providerStatus: str
    providerMessageId: str
    providerPayload: str
    errorMessage: str
    metadata: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
