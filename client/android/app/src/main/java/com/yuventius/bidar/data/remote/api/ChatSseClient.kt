package com.yuventius.bidar.data.remote.api

import com.yuventius.bidar.data.remote.model.BaseResponse
import com.yuventius.bidar.data.remote.model.ChatAnswerRemote
import com.yuventius.bidar.data.remote.model.ChatEventType
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import retrofit2.Retrofit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * BIDAR
 * Class: ChatSseClient
 * Created by Ven Choi on 2026-09-07
 *
 * /chat?use_streaming=true 응답은 text/event-stream(SSE)이라 Retrofit의 일반 suspend
 * 호출로는 받을 수 없다. OkHttp의 EventSource로 직접 구독해 Flow로 흘려보낸다.
 * 프레임 형태(실서버 curl로 확인됨): data: {"code":200,"msg":"success","data":{"event":"SOS"|"TOKEN"|"EOS","token":"..."}}
 */
@Singleton
class ChatSseClient @Inject constructor(
    private val okHttpClient: OkHttpClient,
    retrofit: Retrofit,
    private val json: Json
) {
    private val baseUrl = retrofit.baseUrl()

    fun streamChat(
        query: String,
        documentId: String,
        useOpenAi: Boolean = false
    ): Flow<ChatAnswerRemote> = callbackFlow {
        val url = baseUrl.newBuilder()
            .addPathSegment("chat")
            .addQueryParameter("query", query)
            .addQueryParameter("document_id", documentId)
            .addQueryParameter("use_streaming", "true")
            .addQueryParameter("use_open_ai", useOpenAi.toString())
            .build()

        val request = Request.Builder()
            .url(url)
            .header("Accept", "text/event-stream")
            .post("".toRequestBody(null))
            .build()

        val listener = object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                val answer = runCatching {
                    json.decodeFromString<BaseResponse<ChatAnswerRemote>>(data).data
                }.getOrNull() ?: return

                trySend(answer)
                if (answer.event == ChatEventType.EOS) {
                    close()
                }
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                close(t ?: IllegalStateException("SSE failure: HTTP ${response?.code}"))
            }

            override fun onClosed(eventSource: EventSource) {
                close()
            }
        }

        val eventSource = EventSources.createFactory(okHttpClient).newEventSource(request, listener)

        awaitClose { eventSource.cancel() }
    }
}
