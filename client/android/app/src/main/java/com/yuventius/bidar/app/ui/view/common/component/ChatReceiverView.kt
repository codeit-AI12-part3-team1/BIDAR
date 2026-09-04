package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.theme.MidnightIndigo60
import com.yuventius.bidar.app.ui.theme.SoftGray
import com.yuventius.bidar.app.ui.theme.White
import com.yuventius.bidar.app.util.DatePattern
import com.yuventius.bidar.app.util.formatByDatePattern
import com.yuventius.bidar.domain.model.Chat
import java.time.LocalDateTime

/**
 * BIDAR
 * Class: ChatReceiverView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun ChatReceiverView (
    modifier: Modifier = Modifier,
    chat: Chat = Chat()
) {
    Row (
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Box (
            modifier = Modifier
                .size(24.dp)
                .background(color = MidnightIndigo, shape = CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Text (
                text = "B",
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                color = White
            )
        }

        Column (
            modifier = Modifier,
            horizontalAlignment = Alignment.Start,
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            Box (
                modifier = Modifier
                    .background(color = White, shape = RoundedCornerShape(10.dp)),
                contentAlignment = Alignment.Center
            ) {
                Text (
                    modifier = Modifier
                        .padding(8.dp),
                    text = chat.msg,
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
}

@Preview(showBackground = true)
@Composable
fun ChatReceiverViewPreview() {
    ChatReceiverView()
}