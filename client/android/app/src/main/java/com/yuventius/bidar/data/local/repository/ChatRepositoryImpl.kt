package com.yuventius.bidar.data.local.repository

import com.yuventius.bidar.data.local.ChatDao
import com.yuventius.bidar.data.local.model.ChatWrapper.toData
import com.yuventius.bidar.data.local.model.ChatWrapper.toDomain
import com.yuventius.bidar.domain.model.Chat
import com.yuventius.bidar.domain.repository.ChatRepository
import com.yuventius.bidar.domain.util.LocalDateTimeFormatter
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.time.LocalDateTime
import javax.inject.Inject

/**
 * BIDAR
 * Class: ChatRepositoryImpl
 * Created by Ven Choi on 2026-09-01
 */
class ChatRepositoryImpl @Inject constructor(
    private val chatDao: ChatDao
) : ChatRepository {
    override fun getChats(documentId: String): Flow<List<Chat>> =
        chatDao.getChats(documentId).map { chats -> chats.map { it.toDomain() } }

    override fun getLastChatDate(documentId: String): Flow<LocalDateTime> =
        chatDao.getLastChatDate(documentId).map { LocalDateTimeFormatter.toLocalDateTime(it) }

    override suspend fun insert(chat: Chat): Long = chatDao.insert(chat.toData())

    override suspend fun delete(chat: Chat) = chatDao.delete(chat.toData())
}
