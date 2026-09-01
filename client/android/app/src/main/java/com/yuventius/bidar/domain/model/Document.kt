package com.yuventius.bidar.domain.model

import java.time.LocalDateTime

/**
 * BIDAR
 * Class: Document
 * Created by Ven Choi on 2026-09-01
 */
data class Document (
    val documentId: String = "DOC_000",
    val title: String = "TEST DOCUMENTATION",
    val publishedDate: LocalDateTime = LocalDateTime.now(),
    val fileExt: String = "hwp"
)
