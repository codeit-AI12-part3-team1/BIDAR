package com.yuventius.bidar.data.remote.model

import kotlinx.serialization.Serializable

/**
 * BIDAR
 * Class: BaseResponse
 * Created by Ven Choi on 2026-09-01
 */
@Serializable
data class BaseResponse<T>(
    val code: Int,
    val msg: String,
    val data: T? = null
)
