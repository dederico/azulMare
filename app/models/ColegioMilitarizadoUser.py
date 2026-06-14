from .meta import DirtyTrackingMeta


class ColegioMilitarizadoUser(metaclass=DirtyTrackingMeta):
    __tablename__ = "colegio_militarizado_users"

    area: str
    email: str
    responsable: str
    alias: str
    password_hash: str
    role: str
    campus: str
    is_active: bool
    must_change_password: bool
    created_at: str
    updated_at: str
    last_login_at: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
