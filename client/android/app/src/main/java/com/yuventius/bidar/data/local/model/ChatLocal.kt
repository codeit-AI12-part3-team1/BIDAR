package com.yuventius.bidar.data.local.model

import androidx.room.Entity
import androidx.room.PrimaryKey
import kotlinx.serialization.Serializable

/**
 * BIDAR
 * Class: ChatLocal
 * Created by Ven Choi on 2026-09-01
 */
@Entity(tableName = "chat")
@Serializable
data class ChatLocal (
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0L,
    val documentId: String,
    val msg: String,
    val chatDate: String
)