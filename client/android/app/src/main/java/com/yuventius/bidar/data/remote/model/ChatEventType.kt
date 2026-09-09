package com.yuventius.bidar.data.remote.model

import kotlinx.serialization.Serializable

/**
 * BIDAR
 * Class: ChatEventType
 * Created by Ven Choi on 2026-09-07
 *
 * FULL: 논스트리밍(현재) 응답 - token에 전체 답변이 한 번에 담겨온다.
 * SOS/TOKEN/EOS: 추후 SSE 스트리밍 도입 시 사용 - 스트림 시작/토큰 조각/스트림 종료.
 * UNKNOWN: 알 수 없는 값이 오는 경우의 안전한 기본값(Json.coerceInputValues에 의해 매핑).
 */
@Serializable
enum class ChatEventType {
    FULL,
    SOS,
    TOKEN,
    EOS,
    UNKNOWN
}
