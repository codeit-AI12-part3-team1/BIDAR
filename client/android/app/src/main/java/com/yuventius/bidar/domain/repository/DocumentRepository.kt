package com.yuventius.bidar.domain.repository

import com.yuventius.bidar.domain.model.Document
import java.time.LocalDateTime

/**
 * BIDAR
 * Class: DocumentRepository
 * Created by Ven Choi on 2026-09-01
 */
interface DocumentRepository {
    suspend fun getDocuments(): List<Document>
    suspend fun getChatHistory(documents: List<Document>): List<Document>
}
