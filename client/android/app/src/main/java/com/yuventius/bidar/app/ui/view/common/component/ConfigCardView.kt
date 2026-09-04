package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.yuventius.bidar.R
import com.yuventius.bidar.app.ui.theme.White
import com.yuventius.bidar.app.util.DatePattern
import com.yuventius.bidar.app.util.formatByDatePattern
import com.yuventius.bidar.app.util.noRippleClickable

/**
 * BIDAR
 * Class: ConfigCardView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun ConfigCardView (
    modifier: Modifier = Modifier,
    configTitle: String,
    onClick: () -> Unit = {}
) {
    Row (
        modifier = modifier
            .background(White, shape = RoundedCornerShape(10.dp))
            .padding(8.dp)
            .noRippleClickable(onClick = onClick),
        horizontalArrangement = Arrangement.spacedBy(15.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(configTitle)
        Spacer(Modifier.weight(1F))
        Image (
            painter = painterResource(R.drawable.ic_chevron_right),
            contentDescription = null
        )
    }

}