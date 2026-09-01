package com.yuventius.bidar.domain.repository

import com.yuventius.bidar.domain.model.Chat
import kotlinx.coroutines.flow.Flow
import java.time.LocalDateTime

/**
 * BIDAR
 * Class: ChatRepository
 * Created by Ven Choi on 2026-09-01
 */
interface ChatRepository {
    fun getChats(documentId: String): Flow<List<Chat>>
    fun getLastChatDate(documentId: String): Flow<LocalDateTime>
    suspend fun insert(chat: Chat): Long
    suspend fun delete(chat: Chat)
}
