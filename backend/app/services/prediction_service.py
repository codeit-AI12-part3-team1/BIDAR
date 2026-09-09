from ai.models.predictor import predict as model_predict

def predict(query: str, document_id: str, use_open_ai: bool) -> str:
    if use_open_ai:
        return model_predict(query, document_id, backend="api")
    else:
        return model_predict(query, document_id)

def predict_streaming(query: str, document_id: str):
    # TODO: ai.models.predictor에 predict_streaming 함수가 생기면 아래로 교체
    # from ai.models.predictor import predict_streaming as model_predict_streaming
    # yield from model_predict_streaming(query)
    for word in f"[임시 스트리밍 응답] '{query}'에 대한 답변입니다.".split():
        yield word