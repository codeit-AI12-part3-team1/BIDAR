from fastapi import APIRouter, HTTPException

from app.schemas.schemas import BaseResponse, success, error, TokenResponse, TokenEvent
from app.services.prediction_service import predict

router = APIRouter()


@router.post("/chat", response_model=BaseResponse[TokenResponse])
def evaluate(query: str, use_streaming: bool = False) -> TokenResponse:
    if not use_streaming:
        # streaming 미적용 로직
        result = predict(query)
        return success(data=TokenResponse(
            event=TokenEvent.FULL,
            token=result
        ))
    else:
        # streaming 적용 로직은 추후 구현
        return error(code=501, msg="스트리밍은 아직 지원하지 않습니다.")
