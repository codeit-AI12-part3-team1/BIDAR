package com.yuventius.bidar.app.di

import com.orhanobut.logger.Logger
import okhttp3.Interceptor
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer

/**
 * BIDAR
 * Class: JsonLoggingInterceptor
 * Created by Ven Choi on 2026-09-01
 *
 * 요청/응답 바디를 orhanobut/logger로 pretty print 출력한다.
 */
class JsonLoggingInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        request.body?.let { body ->
            val buffer = Buffer()
            body.writeTo(buffer)
            val requestJson = buffer.readUtf8()
            if (requestJson.isNotBlank()) Logger.json(requestJson)
        }

        val response = chain.proceed(request)
        val responseBody = response.body
        val contentType = responseBody.contentType()

        // SSE(text/event-stream) 응답은 여기서 string()으로 전부 읽어버리면 스트림이 끝날
        // 때까지(EOS) 블로킹되고, 그 사이 데이터가 통째로 버퍼링돼서 EventSource가 이벤트를
        // 실시간이 아니라 한꺼번에 몰아서 받게 된다. 로깅하지 않고 원본 스트림을 그대로 흘려보낸다.
        if (contentType?.type == "text" && contentType.subtype == "event-stream") {
            return response
        }

        val bodyString = responseBody.string()
        if (bodyString.isNotBlank()) Logger.json(bodyString)

        return response.newBuilder()
            .body(bodyString.toResponseBody(contentType))
            .build()
    }
}
