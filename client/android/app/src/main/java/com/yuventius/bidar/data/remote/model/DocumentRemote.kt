package com.yuventius.bidar.data.remote.model

import kotlinx.serialization.Serializable

/**
 * BIDAR
 * Class: DocumentRemote
 * Created by Ven Choi on 2026-09-01
 */
@Serializable
data class DocumentRemote (
    val documentId: String,
    val title: String,
    val publishedDate: String,
    val ext: String
)