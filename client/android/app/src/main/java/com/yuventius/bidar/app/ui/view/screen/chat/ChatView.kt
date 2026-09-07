package com.yuventius.bidar.app.ui.view.screen.chat

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.exclude
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import androidx.paging.LoadState
import androidx.paging.compose.LazyPagingItems
import androidx.paging.compose.collectAsLazyPagingItems
import androidx.paging.compose.itemContentType
import androidx.paging.compose.itemKey
import com.yuventius.bidar.R
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.theme.MidnightIndigo40
import com.yuventius.bidar.app.ui.theme.White
import com.yuventius.bidar.app.ui.view.common.component.ChatDateView
import com.yuventius.bidar.app.ui.view.common.component.ChatReceiverView
import com.yuventius.bidar.app.ui.view.common.component.ChatSenderView
import com.yuventius.bidar.app.ui.view.common.component.ChatTypingView
import com.yuventius.bidar.app.ui.view.common.component.NavHeader
import com.yuventius.bidar.app.ui.view.screen.chat.state.ChatListItem
import com.yuventius.bidar.app.util.noRippleClickable
import com.yuventius.bidar.domain.model.Chat
import com.yuventius.bidar.domain.model.ChatSender
import org.orbitmvi.orbit.compose.collectSideEffect
import java.time.temporal.ChronoUnit

/**
 * BIDAR
 * Class: ChatView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun ChatView (
    modifier: Modifier = Modifier,
    documentTitle: String,
    vm: ChatVM = hiltViewModel(),
    onNavigateBack: () -> Unit = {}
) {
    vm.collectSideEffect {

    }
    val chatItems = vm.chatPagingFlow.collectAsLazyPagingItems()
    val isWaitingForResponse by vm.isWaitingForResponseFlow.collectAsState(initial = false)
    val streamingAnswer by vm.streamingAnswerFlow.collectAsState(initial = null)

    Column (
        modifier = modifier
            // Scaffold의 innerPadding이 이미 navigationBars만큼 하단 여백을 잡아주므로,
            // ime 인셋에서 navigationBars 몫을 제외해 키보드가 뜰 때만큼만 추가로 밀어 올린다.
            .windowInsetsPadding(WindowInsets.ime.exclude(WindowInsets.navigationBars))
    ) {
        NavHeader (
            title = documentTitle,
            onBack = { onNavigateBack() }
        )
        ChatList (
            modifier = Modifier
                .weight(1F)
                .fillMaxWidth(),
            chatItems = chatItems,
            isWaitingForResponse = isWaitingForResponse,
            streamingAnswer = streamingAnswer
        )
        ChatInputBar (
            modifier = Modifier
                .fillMaxWidth(),
            enabled = !isWaitingForResponse,
            onSend = vm::sendMessage
        )
    }
}

@Composable
private fun ChatInputBar (
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    onSend: (String) -> Unit = {}
) {
    var text by remember { mutableStateOf("") }
    val canSend = enabled && text.isNotBlank()
    val inputTextStyle = TextStyle(fontSize = 14.sp, color = White)

    Row (
        modifier = modifier
            .background(MidnightIndigo)
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Box (
            modifier = Modifier
                .weight(1F)
                .background(White.copy(alpha = 0.15F), RoundedCornerShape(20.dp))
                .padding(horizontal = 14.dp, vertical = 10.dp)
        ) {
            if (text.isEmpty()) {
                Text (
                    text = if (enabled) "메시지를 입력하세요" else "답변을 기다리는 중이에요...",
                    style = inputTextStyle.copy(color = White.copy(alpha = 0.5F))
                )
            }
            BasicTextField (
                modifier = Modifier.fillMaxWidth(),
                value = text,
                onValueChange = { text = it },
                enabled = enabled,
                textStyle = inputTextStyle,
                cursorBrush = SolidColor(White),
                maxLines = 4
            )
        }
        Box (
            modifier = Modifier
                .size(40.dp)
                .background(White, CircleShape)
                .noRippleClickable(enabled = canSend) {
                    onSend(text)
                    text = ""
                },
            contentAlignment = Alignment.Center
        ) {
            Image (
                modifier = Modifier.size(18.dp),
                painter = painterResource(R.drawable.ic_send),
                contentDescription = null,
                colorFilter = ColorFilter.tint(if (canSend) MidnightIndigo else MidnightIndigo40)
            )
        }
    }
}

@Composable
private fun ChatList (
    modifier: Modifier = Modifier,
    chatItems: LazyPagingItems<ChatListItem>,
    isWaitingForResponse: Boolean = false,
    streamingAnswer: String? = null
) {
    if (chatItems.loadState.refresh is LoadState.Loading && chatItems.itemCount == 0) {
        Box (
            modifier = modifier,
            contentAlignment = Alignment.Center
        ) {
            CircularProgressIndicator()
        }
        return
    }

    val listState = rememberLazyListState()

    // reverseLayout이라 index 0이 화면 최하단이다. 가장 최신 메시지(id)가 바뀔 때만
    // 최하단으로 스크롤한다 — 과거 메시지를 더 불러와 itemCount만 늘어난 경우엔 반응하지 않는다.
    // itemCount == 0(웰컴 메시지 insert 전 등)일 땐 peek(0)이 IndexOutOfBoundsException을 던지므로 가드한다.
    val newestChatId = if (chatItems.itemCount > 0) {
        (chatItems.peek(0) as? ChatListItem.Message)?.chat?.id
    } else {
        null
    }
    LaunchedEffect(newestChatId, isWaitingForResponse) {
        if (newestChatId != null) {
            listState.animateScrollToItem(0)
        }
    }

    val focusManager = LocalFocusManager.current
    val keyboardController = LocalSoftwareKeyboardController.current

    LazyColumn (
        modifier = modifier
            .noRippleClickable {
                focusManager.clearFocus()
                keyboardController?.hide()
            },
        state = listState,
        reverseLayout = true,
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp)
    ) {
        // reverseLayout이라 여기서 가장 먼저 emit하는 아이템이 화면 최하단에 온다.
        // 스트리밍 토큰이 도착하기 시작하면(streamingAnswer가 비어있지 않으면) 점 3개 대신
        // 실시간으로 채워지는 말풍선을 보여준다.
        if (isWaitingForResponse) {
            item(key = "typing_indicator", contentType = "typing") {
                if (streamingAnswer.isNullOrEmpty()) {
                    ChatTypingView (
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(end = 32.dp, top = 12.dp)
                    )
                } else {
                    ChatReceiverView (
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(end = 32.dp, top = 12.dp),
                        chat = Chat(msg = streamingAnswer, sender = ChatSender.BOT),
                        showTime = false
                    )
                }
            }
        }
        items (
            count = chatItems.itemCount,
            key = chatItems.itemKey { item ->
                when (item) {
                    is ChatListItem.Message -> "message_${item.chat.id}"
                    is ChatListItem.DateSeparator -> "separator_${item.date}"
                }
            },
            contentType = chatItems.itemContentType { item ->
                when (item) {
                    is ChatListItem.Message -> "message"
                    is ChatListItem.DateSeparator -> "separator"
                }
            }
        ) { index ->
            // DESC + reverseLayout이므로 index - 1은 화면상 바로 아래(더 최근) 항목이다.
            val newer = if (index > 0) chatItems[index - 1] else null

            when (val item = chatItems[index]) {
                is ChatListItem.Message -> {
                    val newerAsMessage = newer as? ChatListItem.Message
                    // 같은 발신자가 연속되면 4dp, 발신자가 바뀌거나(날짜 구분자 포함) 처음 항목이면 12dp.
                    // index(자신)의 bottom에 적용해야 비교 대상인 index - 1(화면상 바로 아래)과의
                    // 경계에 간격이 들어간다 — top에 넣으면 엉뚱하게 index + 1과의 경계에 적용돼버린다.
                    val bottomSpacing = when {
                        index == 0 -> 0.dp
                        newerAsMessage != null && newerAsMessage.chat.sender == item.chat.sender -> 4.dp
                        else -> 12.dp
                    }
                    // 같은 발신자·같은 분 단위 시각이면 시간 표시는 최근 메시지(화면상 더 아래)에만 남긴다.
                    val showTime = newerAsMessage == null ||
                        newerAsMessage.chat.sender != item.chat.sender ||
                        !newerAsMessage.chat.chatDate.truncatedTo(ChronoUnit.MINUTES)
                            .isEqual(item.chat.chatDate.truncatedTo(ChronoUnit.MINUTES))

                    when (item.chat.sender) {
                        ChatSender.USER -> ChatSenderView (
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(start = 32.dp, bottom = bottomSpacing),
                            chat = item.chat,
                            showTime = showTime
                        )
                        ChatSender.BOT -> ChatReceiverView (
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(end = 32.dp, bottom = bottomSpacing),
                            chat = item.chat,
                            showTime = showTime
                        )
                    }
                }
                is ChatListItem.DateSeparator -> Box (
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = if (index == 0) 0.dp else 12.dp),
                    contentAlignment = Alignment.Center
                ) {
                    ChatDateView(localDateTime = item.date)
                }
                null -> Unit
            }
        }
    }
}