package com.yuventius.bidar.data.remote.model

import kotlinx.serialization.Serializable

/**
 * BIDAR
 * Class: ChatAnswerRemote
 * Created by Ven Choi on 2026-09-07
 */
@Serializable
data class ChatAnswerRemote (
    val event: ChatEventType = ChatEventType.UNKNOWN,
    val token: String
)
