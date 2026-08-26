from fastapi import APIRouter, HTTPException

from app.schemas.schemas import BaseResponse, success
from app.services.prediction_service import predict

router = APIRouter()


@router.post("/chat", response_model=BaseResponse[str])
def evaluate(query: str, use_streaming: bool = False) -> BaseResponse[str]:
    if not use_streaming:
        # streaming 미적용 로직
        result = predict(query)
        return success(data=result)
    else:
        # streaming 적용 로직은 추후 구현
        raise HTTPException(status_code=501, detail="스트리밍은 아직 지원하지 않습니다.")
