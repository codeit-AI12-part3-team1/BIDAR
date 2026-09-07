package com.yuventius.bidar.data.remote.model

import com.yuventius.bidar.domain.model.Document
import com.yuventius.bidar.domain.util.BaseWrapper
import com.yuventius.bidar.domain.util.LocalDateTimeFormatter

/**
 * BIDAR
 * Class: DocumentWrapper
 * Created by Ven Choi on 2026-09-01
 */
object DocumentWrapper : BaseWrapper<Document, DocumentRemote>() {
    override fun Document.toData(): DocumentRemote = DocumentRemote(
        documentId = documentId,
        title = title,
        publishedDate = LocalDateTimeFormatter.toTimeString(publishedDate),
        ext = fileExt
    )

    override fun DocumentRemote.toDomain(): Document = Document(
        documentId = documentId,
        title = title,
        publishedDate = LocalDateTimeFormatter.toLocalDateTime(publishedDate),
        fileExt = ext
    )
}
