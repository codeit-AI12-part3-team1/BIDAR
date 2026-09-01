package com.yuventius.bidar.data.remote.repository

import com.yuventius.bidar.data.remote.api.DocumentApi
import com.yuventius.bidar.data.remote.model.DocumentWrapper.toDomain
import com.yuventius.bidar.domain.model.Document
import com.yuventius.bidar.domain.repository.DocumentRepository
import javax.inject.Inject

/**
 * BIDAR
 * Class: DocumentRepositoryImpl
 * Created by Ven Choi on 2026-09-01
 */
class DocumentRepositoryImpl @Inject constructor(
    private val documentApi: DocumentApi
) : DocumentRepository {
    override suspend fun getDocuments(): List<Document> =
        documentApi.getDocuments().data.orEmpty().map { it.toDomain() }
}
