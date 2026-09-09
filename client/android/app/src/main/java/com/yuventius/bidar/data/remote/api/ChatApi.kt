package com.yuventius.bidar.data.remote.api

import com.yuventius.bidar.data.remote.model.BaseResponse
import com.yuventius.bidar.data.remote.model.ChatAnswerRemote
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * BIDAR
 * Class: ChatApi
 * Created by Ven Choi on 2026-09-07
 *
 * /chat은 JSON 바디가 아니라 쿼리 파라미터로 요청을 받는다(백엔드 FastAPI 시그니처 확인됨).
 */
interface ChatApi {
    @POST("chat")
    suspend fun postChat(
        @Query("query") query: String,
        @Query("document_id") documentId: String,
        @Query("use_streaming") useStreaming: Boolean,
        @Query("use_open_ai") useOpenAi: Boolean
    ): BaseResponse<ChatAnswerRemote>
}
