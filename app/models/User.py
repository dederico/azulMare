class User:
    username: str
    password: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)