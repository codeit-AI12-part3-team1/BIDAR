package com.yuventius.bidar.app.ui.view.common.component

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import java.time.LocalDateTime

/**
 * BIDAR
 * Class: ChatReceiverView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun ChatReceiverView (
    modifier: Modifier = Modifier,
    receiver: String = "BIDAR AI",
    msg: String = "TEST MSG",
    localDateTime: LocalDateTime = LocalDateTime.now()
) {

}