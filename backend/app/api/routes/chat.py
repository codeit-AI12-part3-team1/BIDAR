import asyncio
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from app.schemas.schemas import BaseResponse, success, TokenResponse, TokenEvent
from app.services.prediction_service import predict, predict_streaming

router = APIRouter()


@router.post("/chat", response_model=BaseResponse[TokenResponse])
def evaluate(query: str, document_id: str, use_streaming: bool = False):
    if not use_streaming:
        # streaming 미적용 로직
        result = predict(query, document_id)
        return success(data=TokenResponse(
            event=TokenEvent.FULL,
            token=result
        ))
    else:
        # streaming 적용 로직
        async def event_generator():
            yield {"data": success(data=TokenResponse(event=TokenEvent.SOS, token="")).model_dump_json()}

            for token in predict_streaming(query, document_id):
                # FIXME: 실제 AI 모듈에서 구현한 방식에 따라 async 처리가 필요 (하단 sleep 제거 후 적용)
                await asyncio.sleep(0.2)
                yield {"data": success(data=TokenResponse(event=TokenEvent.TOKEN, token=token)).model_dump_json()}

            yield {"data": success(data=TokenResponse(event=TokenEvent.EOS, token="")).model_dump_json()}

        return EventSourceResponse(event_generator())
