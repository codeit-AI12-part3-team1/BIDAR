from typing import Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    code: int
    msg: str
    data: Optional[T] = None


def success(data: Optional[T] = None, msg: str = "success", code: int = 200) -> BaseResponse[T]:
    return BaseResponse[T](code=code, msg=msg, data=data)


def error(msg: str = "error", code: int = 500, data: Optional[T] = None) -> BaseResponse[T]:
    return BaseResponse[T](code=code, msg=msg, data=data)

# SSE 전용 Response
class TokenResponse(BaseModel):
    event: str
    token: str