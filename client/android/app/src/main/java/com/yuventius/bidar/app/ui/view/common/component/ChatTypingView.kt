package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.StartOffset
import androidx.compose.animation.core.StartOffsetType
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.theme.White

/**
 * BIDAR
 * Class: ChatTypingView
 * Created by Ven Choi on 2026-09-07
 *
 * 봇 응답을 대기하는 동안 ChatReceiverView 자리에 대신 보여주는 점 3개 타이핑 인디케이터.
 */
@Composable
fun ChatTypingView (
    modifier: Modifier = Modifier
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

        Row (
            modifier = Modifier
                .background(color = White, shape = RoundedCornerShape(10.dp))
                .padding(horizontal = 12.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            repeat(3) { index ->
                TypingDot(delayMillis = index * 150)
            }
        }
    }
}

@Composable
private fun TypingDot (
    delayMillis: Int
) {
    val transition = rememberInfiniteTransition(label = "chatTypingDot")
    val alpha by transition.animateFloat (
        initialValue = 0.3F,
        targetValue = 1F,
        animationSpec = infiniteRepeatable (
            animation = tween(durationMillis = 600, easing = LinearEasing),
            repeatMode = RepeatMode.Reverse,
            initialStartOffset = StartOffset(delayMillis, StartOffsetType.Delay)
        ),
        label = "chatTypingDotAlpha"
    )

    Box (
        modifier = Modifier
            .size(6.dp)
            .alpha(alpha)
            .background(color = MidnightIndigo, shape = CircleShape)
    )
}

@Preview(showBackground = true)
@Composable
fun ChatTypingViewPreview() {
    ChatTypingView()
}
