from .meta import DirtyTrackingMeta


class OutgoingCampaign(metaclass=DirtyTrackingMeta):
    name: str
    audienceName: str
    audienceFileId: int
    message: str
    messageMode: str
    campaignKind: str
    approvedTemplateName: str
    approvedTemplateLocale: str
    approvedTemplateVariables: str
    followupDelayMinutes: int
    attachmentUrl: str
    attachmentFilename: str
    returnToSamEnabled: bool
    returnToSamMessage: str
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
