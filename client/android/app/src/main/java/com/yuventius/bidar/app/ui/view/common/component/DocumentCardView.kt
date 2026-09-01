package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.yuventius.bidar.R
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
            .noRippleClickable(onClick = onClick),
        horizontalArrangement = Arrangement.spacedBy(15.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Image (
            painter = painterResource(R.drawable.ic_document),
            contentDescription = null
        )
        Column (
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(document.title)
            val dateString = document.lastChatDate?.formatByDatePattern(DatePattern.CHAT_HISTORY) ?: "없음"
            Text("최종채팅일자: $dateString")
        }
        Spacer(Modifier.weight(1F))
        Image (
            painter = painterResource(R.drawable.ic_chevron_right),
            contentDescription = null
        )
    }
}