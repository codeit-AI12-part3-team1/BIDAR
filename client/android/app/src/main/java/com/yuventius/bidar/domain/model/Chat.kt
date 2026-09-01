package com.yuventius.bidar.domain.model

import java.time.LocalDateTime

/**
 * BIDAR
 * Class: Chat
 * Created by Ven Choi on 2026-09-01
 */
data class Chat (
    val id: Long = -1L,
    val documentId: String = "DOC_000",
    val msg: String = "TEST MSG",
    val chatDate: LocalDateTime = LocalDateTime.now()
)
