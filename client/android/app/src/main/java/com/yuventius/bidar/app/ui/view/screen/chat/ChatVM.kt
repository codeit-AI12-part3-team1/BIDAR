package com.yuventius.bidar.app.ui.view.screen.chat

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.paging.PagingData
import androidx.paging.cachedIn
import androidx.paging.insertSeparators
import androidx.paging.map
import com.yuventius.bidar.app.navigation.Route
import com.yuventius.bidar.app.ui.view.screen.chat.state.ChatListItem
import com.yuventius.bidar.app.ui.view.screen.chat.state.ChatSideEffect
import com.yuventius.bidar.app.ui.view.screen.chat.state.ChatState
import com.yuventius.bidar.domain.model.Chat
import com.yuventius.bidar.domain.model.ChatSender
import com.yuventius.bidar.domain.repository.ChatRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.emitAll
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.map
import org.orbitmvi.orbit.OrbitContainerHost
import org.orbitmvi.orbit.viewmodel.orbitContainer
import java.time.LocalDateTime
import javax.inject.Inject

/**
 * BIDAR
 * Class: ChatVM
 * Created by Ven Choi on 2026-09-01
 */
@HiltViewModel
class ChatVM @Inject constructor (
    savedStateHandle: SavedStateHandle,
    private val chatRepository: ChatRepository
): OrbitContainerHost<ChatState, ChatState, ChatSideEffect>, ViewModel() {
    private val documentId: String = checkNotNull(savedStateHandle[Route.Chat.ARG_DOCUMENT_ID])

    override val container = orbitContainer<ChatState, ChatSideEffect>(ChatState)

    // documentId 기준 최신순(DESC) 스트림이므로, before가 after보다 항상 최근 메시지다.
    // Pager를 만들기 전에 웰컴 메시지 체크/삽입을 먼저 끝내서, "리스트가 처음엔 빈 상태로
    // 로드되고 뒤늦게 insert된 웰컴 메시지가 반영 안 되는" 레이스를 없앤다.
    val chatPagingFlow: Flow<PagingData<ChatListItem>> =
        flow {
            ensureWelcomeMessage()
            emitAll(chatRepository.getChats(documentId))
        }
            .map { pagingData ->
                pagingData
                    .map { chat -> ChatListItem.Message(chat) }
                    .insertSeparators<ChatListItem.Message, ChatListItem> { before, after ->
                        when {
                            before == null -> null
                            after == null || before.chat.chatDate.toLocalDate() != after.chat.chatDate.toLocalDate() ->
                                ChatListItem.DateSeparator(before.chat.chatDate)
                            else -> null
                        }
                    }
            }
            .cachedIn(viewModelScope)

    // 화면(ViewModel) 생명주기와 무관하게 리포지토리가 들고 있는 대기 상태를 그대로 구독한다.
    // 화면을 나갔다 재진입해도 응답이 아직 안 왔다면 true로 다시 관측된다.
    val isWaitingForResponseFlow: Flow<Boolean> = chatRepository.isWaitingForResponse(documentId)

    // SSE 스트리밍 중 지금까지 도착한 텍스트. 스트리밍 중이 아니면 null(=3점 타이핑 인디케이터 표시).
    val streamingAnswerFlow: Flow<String?> = chatRepository.streamingAnswer(documentId)

    fun sendMessage(msg: String) {
        val trimmed = msg.trim()
        if (trimmed.isEmpty()) return

        chatRepository.sendMessage(documentId, trimmed)
    }

    private suspend fun ensureWelcomeMessage() {
        if (chatRepository.getChatCount(documentId) > 0) return

        chatRepository.insert(
            Chat(
                id = NEW_CHAT_ID,
                documentId = documentId,
                msg = WELCOME_MESSAGE,
                chatDate = LocalDateTime.now(),
                sender = ChatSender.BOT
            )
        )
    }

    companion object {
        // Room의 @PrimaryKey(autoGenerate = true)는 0L을 넘겨야 새 id를 채번한다.
        private const val NEW_CHAT_ID = 0L
        private const val WELCOME_MESSAGE =
            "안녕하세요 챗봇 BIDAR 입니다. 선택하신 문서에 궁금한 점이 있다면 언제든 물어보세요!"
    }
}
