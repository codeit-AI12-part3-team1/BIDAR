package com.yuventius.bidar.data.local.repository

import androidx.paging.Pager
import androidx.paging.PagingConfig
import androidx.paging.PagingData
import androidx.paging.map
import com.yuventius.bidar.app.di.ApplicationScope
import com.yuventius.bidar.data.local.ChatDao
import com.yuventius.bidar.data.local.model.ChatWrapper.toData
import com.yuventius.bidar.data.local.model.ChatWrapper.toDomain
import com.yuventius.bidar.data.remote.api.ChatApi
import com.yuventius.bidar.data.remote.api.ChatSseClient
import com.yuventius.bidar.data.remote.model.ChatEventType
import com.yuventius.bidar.domain.model.Chat
import com.yuventius.bidar.domain.model.ChatSender
import com.yuventius.bidar.domain.repository.ChatRepository
import com.yuventius.bidar.domain.util.LocalDateTimeFormatter
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import javax.inject.Inject

/**
 * BIDAR
 * Class: ChatRepositoryImpl
 * Created by Ven Choi on 2026-09-01
 */
class ChatRepositoryImpl @Inject constructor(
    private val chatDao: ChatDao,
    private val chatApi: ChatApi,
    private val chatSseClient: ChatSseClient,
    @ApplicationScope private val appScope: CoroutineScope
) : ChatRepository {
    private val waitingDocumentIds = MutableStateFlow<Set<String>>(emptySet())
    private val streamingAnswers = MutableStateFlow<Map<String, String>>(emptyMap())

    // 메모리에만 두는 세션 한정 옵션 - 프로세스가 새로 시작되면 항상 false로 리셋된다.
    private val _useStreaming = MutableStateFlow(false)
    override val useStreaming: StateFlow<Boolean> = _useStreaming.asStateFlow()

    private val _useOpenAi = MutableStateFlow(false)
    override val useOpenAi: StateFlow<Boolean> = _useOpenAi.asStateFlow()

    override fun setUseStreaming(enabled: Boolean) {
        _useStreaming.value = enabled
    }

    override fun setUseOpenAi(enabled: Boolean) {
        _useOpenAi.value = enabled
    }

    override fun getChats(documentId: String): Flow<PagingData<Chat>> =
        Pager(
            config = PagingConfig(pageSize = CHAT_PAGE_SIZE, enablePlaceholders = false),
            pagingSourceFactory = { chatDao.getChats(documentId) }
        ).flow.map { pagingData -> pagingData.map { it.toDomain() } }

    override fun getLastChatDate(documentId: String): Flow<LocalDateTime?> =
        chatDao.getLastChatDate(documentId).map { it?.let(LocalDateTimeFormatter::toLocalDateTime) }

    override suspend fun getChatCount(documentId: String): Int = chatDao.getChatCount(documentId)

    override suspend fun insert(chat: Chat): Long = chatDao.insert(chat.toData())

    override suspend fun delete(chat: Chat) = chatDao.delete(chat.toData())

    override suspend fun deleteAll() = chatDao.deleteAll()

    override fun isWaitingForResponse(documentId: String): Flow<Boolean> =
        waitingDocumentIds.map { documentId in it }

    override fun streamingAnswer(documentId: String): Flow<String?> =
        streamingAnswers.map { it[documentId] }

    override fun sendMessage(documentId: String, query: String) {
        appScope.launch {
            waitingDocumentIds.update { it + documentId }
            try {
                insert(
                    Chat(
                        id = NEW_CHAT_ID,
                        documentId = documentId,
                        msg = query,
                        chatDate = LocalDateTime.now(),
                        sender = ChatSender.USER
                    )
                )

                val answer = if (useStreaming.value) {
                    requestStreamingAnswer(documentId, query)
                } else {
                    runCatching { requestAnswer(documentId, query) }.getOrElse { ANSWER_ERROR_MESSAGE }
                }

                insert(
                    Chat(
                        id = NEW_CHAT_ID,
                        documentId = documentId,
                        msg = answer,
                        chatDate = LocalDateTime.now(),
                        sender = ChatSender.BOT
                    )
                )
            } finally {
                streamingAnswers.update { it - documentId }
                waitingDocumentIds.update { it - documentId }
            }
        }
    }

    private suspend fun requestAnswer(documentId: String, query: String): String {
        val response = chatApi.postChat(
            query = query,
            documentId = documentId,
            // 이 호출은 논스트리밍 전용 경로다. useStreaming이 켜져 있으면 sendMessage가 아예
            // requestStreamingAnswer로 분기하므로 여기서는 항상 false로 보낸다 - true로 보내면
            // 서버가 text/event-stream을 내려주는데 이 Retrofit 호출은 단일 JSON 응답만 파싱할 수 있다.
            useStreaming = false,
            useOpenAi = useOpenAi.value
        )
        return requireNotNull(response.data) { "chat response data is null: $response" }.token
    }

    // 토큰마다 DB에 쓰면 Paging이 매번 다시 로드돼 비효율적이므로, 진행 중 텍스트는
    // streamingAnswers(메모리)에만 쌓고 완료됐을 때 한 번만 최종 텍스트를 반환해 insert시킨다.
    private suspend fun requestStreamingAnswer(documentId: String, query: String): String {
        val builder = StringBuilder()
        val result = runCatching {
            chatSseClient.streamChat(
                query = query,
                documentId = documentId,
                useOpenAi = useOpenAi.value
            ).collect { event ->
                if (event.event == ChatEventType.TOKEN) {
                    // 토큰 사이는 공백으로 구분하되, 마지막 토큰 뒤에 남는 공백은 완료 시점에 trim한다.
                    builder.append(event.token).append(' ')
                    streamingAnswers.update { it + (documentId to builder.toString().trimEnd()) }
                }
            }
        }

        return result.fold(
            onSuccess = { builder.toString().trimEnd().ifBlank { ANSWER_ERROR_MESSAGE } },
            onFailure = { ANSWER_ERROR_MESSAGE }
        )
    }

    companion object {
        private const val CHAT_PAGE_SIZE = 30

        // Room의 @PrimaryKey(autoGenerate = true)는 0L을 넘겨야 새 id를 채번한다.
        private const val NEW_CHAT_ID = 0L
        private const val ANSWER_ERROR_MESSAGE =
            "죄송해요, 답변을 가져오지 못했어요. 잠시 후 다시 시도해주세요."
    }
}
