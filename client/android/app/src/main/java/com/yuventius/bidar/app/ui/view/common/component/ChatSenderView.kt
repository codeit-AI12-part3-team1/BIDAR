package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.theme.MidnightIndigo60
import com.yuventius.bidar.app.ui.theme.White
import com.yuventius.bidar.app.util.DatePattern
import com.yuventius.bidar.app.util.formatByDatePattern
import com.yuventius.bidar.domain.model.Chat
import java.time.LocalDateTime

/**
 * BIDAR
 * Class: ChatSenderView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun ChatSenderView (
    modifier: Modifier = Modifier,
    chat: Chat = Chat()
) {
    Column (
        modifier = modifier,
        horizontalAlignment = Alignment.End
    ) {
        Box (
            modifier = Modifier
                .background(MidnightIndigo, shape = RoundedCornerShape(10.dp))
        ) {
            Text (
                modifier = Modifier
                    .padding(8.dp),
                text = chat.msg,
                color = White,
                fontSize = 12.sp
            )
        }

        Text (
            text = chat.chatDate.formatByDatePattern(DatePattern.CHAT_TIME),
            fontSize = 10.sp,
            color = MidnightIndigo60
        )
    }
}