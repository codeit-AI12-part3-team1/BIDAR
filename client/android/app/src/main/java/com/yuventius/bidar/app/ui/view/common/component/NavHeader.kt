package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.yuventius.bidar.R
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.util.noRippleClickable

/**
 * BIDAR
 * Class: NavHeader
 * Created by Ven Choi on 2026-09-07
 */
@Composable
fun NavHeader (
    modifier: Modifier = Modifier,
    title: String = "Test",
    onBack: (Any?) -> Unit = {}
) {
    Row (
        modifier = modifier
            .background(MidnightIndigo)
            .padding(vertical = 12.dp)
            .padding(end = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Image (
            modifier = Modifier
                .size(50.dp)
                .noRippleClickable {
                    onBack.invoke(null)
                },
            painter = painterResource(R.drawable.ic_chevron_left),
            contentDescription = null,
            colorFilter = ColorFilter.tint(Color.White)
        )
        Spacer(modifier = Modifier.weight(1F))
        Text (
            text = title,
            fontWeight = FontWeight.Bold,
            fontSize = 16.sp,
            color = Color.White
        )
    }
}