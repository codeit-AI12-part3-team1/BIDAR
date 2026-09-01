package com.yuventius.bidar.app.ui.view.screen.chat

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

/**
 * BIDAR
 * Class: ChatView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun ChatView (
    modifier: Modifier = Modifier,
    documentId: String,
    onNavigateBack: () -> Unit = {}
) {
    Box (
        modifier = modifier
            .fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column (
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("CHAT VIEW")
            Text("documentId is \"$documentId\"")
            Button(onClick = onNavigateBack) {
                Text("back")
            }
        }
    }
}