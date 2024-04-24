from pydantic import BaseModel

class User:
    username: str
    password: str

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class UserInDB(BaseModel):
    id: int
    password: str

class UserInLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str