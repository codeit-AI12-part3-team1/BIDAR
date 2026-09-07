package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.yuventius.bidar.R
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.theme.White
import com.yuventius.bidar.app.util.DatePattern
import com.yuventius.bidar.app.util.formatByDatePattern
import com.yuventius.bidar.app.util.noRippleClickable
import com.yuventius.bidar.domain.model.Document

/**
 * BIDAR
 * Class: DocumentCardView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun DocumentCardView (
    modifier: Modifier = Modifier,
    document: Document = Document(),
    onClick: () -> Unit = {}
) {
    Row (
        modifier = modifier
            .background(Color.White, shape = RoundedCornerShape(10.dp))
            .padding(8.dp)
            .noRippleClickable(onClick = onClick),
        horizontalArrangement = Arrangement.spacedBy(15.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Image (
            modifier = Modifier
                .size(40.dp),
            painter = painterResource(R.drawable.ic_document),
            contentDescription = null,
            colorFilter = ColorFilter.tint(MidnightIndigo)
        )
        Column (
            modifier = Modifier
                .weight(1F),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(document.title)
            val dateString = document.lastChatDate?.formatByDatePattern(DatePattern.CHAT_HISTORY) ?: "없음"
            Text (
                "최종채팅일자: $dateString",
                fontSize = 12.sp,
                color = Color.LightGray
            )
        }
        Image (
            modifier = Modifier
                .size(24.dp),
            painter = painterResource(R.drawable.ic_chevron_right),
            contentDescription = null
        )
    }
}