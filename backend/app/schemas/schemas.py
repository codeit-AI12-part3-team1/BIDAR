from typing import Generic, Optional, TypeVar
from pydantic import BaseModel
from enum import Enum

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    code: int
    msg: str
    data: Optional[T] = None


def success(data: Optional[T] = None, msg: str = "success", code: int = 200) -> BaseResponse[T]:
    return BaseResponse[T](code=code, msg=msg, data=data)


def error(msg: str = "error", code: int = 500, data: Optional[T] = None) -> BaseResponse[T]:
    return BaseResponse[T](code=code, msg=msg, data=data)

class TokenEvent(str, Enum):
    FULL = "FULL"
    SOS = "SOS"
    TOKEN = "TOKEN"
    EOS = "EOS"


class TokenResponse(BaseModel):
    event: TokenEvent
    token: str

class Document(BaseModel):
    file_name: str
    document_id: str