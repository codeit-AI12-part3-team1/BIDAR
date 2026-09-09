package com.yuventius.bidar.data.remote.repository

import com.yuventius.bidar.data.remote.api.DocumentApi
import com.yuventius.bidar.data.remote.model.DocumentWrapper.toDomain
import com.yuventius.bidar.domain.model.Document
import com.yuventius.bidar.domain.repository.ChatRepository
import com.yuventius.bidar.domain.repository.DocumentRepository
import kotlinx.coroutines.flow.first
import java.time.LocalDateTime
import javax.inject.Inject

/**
 * BIDAR
 * Class: DocumentRepositoryImpl
 * Created by Ven Choi on 2026-09-01
 */
class DocumentRepositoryImpl @Inject constructor(
    private val documentApi: DocumentApi,
    private val chatRepository: ChatRepository
) : DocumentRepository {
    override suspend fun getDocuments(): List<Document> =
        documentApi.getDocuments().data.orEmpty().map { remote ->
            val document = remote.toDomain()
            document.copy(lastChatDate = chatRepository.getLastChatDate(document.documentId).first())
        }

    override suspend fun getChatHistory(documents: List<Document>): List<Document> = documents.map { document ->
        document.copy(lastChatDate = chatRepository.getLastChatDate(document.documentId).first())
    }
}
