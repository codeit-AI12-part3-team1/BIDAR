package com.yuventius.bidar.data.remote.api

import com.yuventius.bidar.data.remote.model.BaseResponse
import com.yuventius.bidar.data.remote.model.DocumentRemote
import retrofit2.http.GET

/**
 * BIDAR
 * Class: DocumentApi
 * Created by Ven Choi on 2026-09-01
 */
interface DocumentApi {
    @GET("documents")
    suspend fun getDocuments(): BaseResponse<List<DocumentRemote>>
}