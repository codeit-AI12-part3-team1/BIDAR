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
        val bodyString = responseBody.string()
        if (bodyString.isNotBlank()) Logger.json(bodyString)

        return response.newBuilder()
            .body(bodyString.toResponseBody(responseBody.contentType()))
            .build()
    }
}
