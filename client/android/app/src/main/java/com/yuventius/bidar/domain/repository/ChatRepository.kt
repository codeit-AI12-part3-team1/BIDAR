package com.yuventius.bidar.domain.repository

import androidx.paging.PagingData
import com.yuventius.bidar.domain.model.Chat
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow
import java.time.LocalDateTime

/**
 * BIDAR
 * Class: ChatRepository
 * Created by Ven Choi on 2026-09-01
 */
interface ChatRepository {
    fun getChats(documentId: String): Flow<PagingData<Chat>>
    fun getLastChatDate(documentId: String): Flow<LocalDateTime?>
    suspend fun getChatCount(documentId: String): Int
    suspend fun insert(chat: Chat): Long
    suspend fun delete(chat: Chat)
    suspend fun deleteAll()

    /** documentId의 응답 대기 여부. 화면(ViewModel) 생명주기와 무관하게 유지된다. */
    fun isWaitingForResponse(documentId: String): Flow<Boolean>

    /** SSE 스트리밍 중 지금까지 도착한 토큰을 이어 붙인 텍스트. 스트리밍 중이 아니면 null. */
    fun streamingAnswer(documentId: String): Flow<String?>

    /**
     * 사용자 메시지 저장 -> 챗봇 응답 요청 -> 응답 저장까지 전체를 화면과 무관한 스코프에서 수행한다.
     * 화면을 나가도(ViewModel이 정리돼도) 계속 진행되고, 재진입 시 isWaitingForResponse로 진행 상태를 확인할 수 있다.
     */
    fun sendMessage(documentId: String, query: String)

    /**
     * 채팅 요청 옵션(Setting 화면 토글). 메모리에만 두므로 앱을 새로 시작하면 항상 false로 리셋된다.
     */
    val useStreaming: StateFlow<Boolean>
    val useOpenAi: StateFlow<Boolean>
    fun setUseStreaming(enabled: Boolean)
    fun setUseOpenAi(enabled: Boolean)
}
