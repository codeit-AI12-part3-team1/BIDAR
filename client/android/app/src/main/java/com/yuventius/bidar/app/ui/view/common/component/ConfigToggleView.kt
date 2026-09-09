package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.theme.White

/**
 * BIDAR
 * Class: ConfigToggleView
 * Created by Ven Choi on 2026-09-07
 */
@Composable
fun ConfigToggleView (
    modifier: Modifier = Modifier,
    configTitle: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit = {}
) {
    Row (
        modifier = modifier
            .background(White, shape = RoundedCornerShape(10.dp))
            .padding(horizontal = 12.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(15.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(configTitle)
        Spacer(Modifier.weight(1F))
        Switch (
            checked = checked,
            onCheckedChange = onCheckedChange,
            colors = SwitchDefaults.colors(checkedTrackColor = MidnightIndigo)
        )
    }
}
