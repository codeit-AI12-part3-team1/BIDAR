def predict(query: str, document_id: str) -> str:
    # TODO: ai.models.predictor에 predict 함수가 생기면 아래로 교체
    # from ai.models.predictor import predict as model_predict
    # return model_predict(query)
    return f"[임시 응답] '{query}'에 대한 답변입니다."

def predict_streaming(query: str, document_id: str):
    # TODO: ai.models.predictor에 predict_streaming 함수가 생기면 아래로 교체
    # from ai.models.predictor import predict_streaming as model_predict_streaming
    # yield from model_predict_streaming(query)
    for word in f"[임시 스트리밍 응답] '{query}'에 대한 답변입니다.".split():
        yield word