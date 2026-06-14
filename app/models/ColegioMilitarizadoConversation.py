from .meta import DirtyTrackingMeta


class ColegioMilitarizadoConversation(metaclass=DirtyTrackingMeta):
    __tablename__ = "colegio_militarizado_conversations"

    session_id: str
    user_email: str
    role: str
    content: str
    created_at: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
