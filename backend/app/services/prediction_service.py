from ai.models.predictor import predict as model_predict

def predict(query: str, document_id: str, use_open_ai: bool) -> str:
    if use_open_ai:
        return "미구현"
    else:
        return model_predict(query, document_id)

def predict_streaming(query: str, document_id: str, use_open_ai: bool):
    # TODO: ai.models.predictor에 predict_streaming 함수가 생기면 아래로 교체
    # from ai.models.predictor import predict_streaming as model_predict_streaming
    # yield from model_predict_streaming(query)
    if use_open_ai:
        for word in f"해당 기능은 미구현 상태입니다.".split():
            yield word
    else:
        for word in f"[임시 스트리밍 응답] '{query}'에 대한 답변입니다.".split():
            yield word