package com.yuventius.bidar.data.local.model

import com.yuventius.bidar.domain.model.Chat
import com.yuventius.bidar.domain.util.BaseWrapper
import com.yuventius.bidar.domain.util.LocalDateTimeFormatter

/**
 * BIDAR
 * Class: ChatWrapper
 * Created by Ven Choi on 2026-09-01
 */
object ChatWrapper : BaseWrapper<Chat, ChatLocal>() {
    override fun Chat.toData(): ChatLocal = ChatLocal(
        id = id,
        documentId = documentId,
        msg = msg,
        chatDate = LocalDateTimeFormatter.toTimeString(chatDate)
    )

    override fun ChatLocal.toDomain(): Chat = Chat(
        id = id,
        documentId = documentId,
        msg = msg,
        chatDate = LocalDateTimeFormatter.toLocalDateTime(chatDate)
    )
}
