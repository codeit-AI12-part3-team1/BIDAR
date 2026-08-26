from fastapi import APIRouter

from app.schemas.schemas import BaseResponse, success

router = APIRouter()


@router.get("/health", response_model=BaseResponse[str])
def health_check() -> BaseResponse[str]:
    return success(data="ok")
