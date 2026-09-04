package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.yuventius.bidar.app.ui.theme.MidnightIndigo40
import com.yuventius.bidar.app.ui.theme.White60
import com.yuventius.bidar.app.util.DatePattern
import com.yuventius.bidar.app.util.formatByDatePattern
import java.time.LocalDateTime

/**
 * BIDAR
 * Class: ChatDateView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun ChatDateView (
    modifier: Modifier = Modifier,
    localDateTime: LocalDateTime = LocalDateTime.now()
) {
    Box (
        modifier = modifier
            .background (
                color = MidnightIndigo40,
                shape = RoundedCornerShape(10.dp)
            )
            .padding(4.dp),
        contentAlignment = Alignment.Center
    ) {
        Text (
            localDateTime.formatByDatePattern(DatePattern.CHAT_DATE),
            color = White60,
            fontSize = 10.sp
        )
    }
}