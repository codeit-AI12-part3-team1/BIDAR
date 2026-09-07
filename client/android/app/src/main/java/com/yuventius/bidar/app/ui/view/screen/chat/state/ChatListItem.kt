package com.yuventius.bidar.app.ui.view.screen.chat.state

import com.yuventius.bidar.domain.model.Chat
import java.time.LocalDateTime

/**
 * BIDAR
 * Class: ChatListItem
 * Created by Ven Choi on 2026-09-07
 *
 * Paging3의 insertSeparators로 [Chat] 스트림 사이에 날짜 구분자를 끼워 넣기 위한 래퍼.
 */
sealed class ChatListItem {
    data class Message(val chat: Chat) : ChatListItem()
    data class DateSeparator(val date: LocalDateTime) : ChatListItem()
}
