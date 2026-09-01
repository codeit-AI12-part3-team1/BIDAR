package com.yuventius.bidar.app.ui.view.screen.home

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

/**
 * BIDAR
 * Class: HomeView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun HomeView (
    modifier: Modifier = Modifier,
    onNavigateToChat: (String) -> Unit = {}
) {
    Box (
        modifier = modifier
            .fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column (
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("HOME VIEW")
            Button (
                onClick = {
                    onNavigateToChat.invoke("DOC_001")
                }
            ) {
                Text("Navigate To \"DOC_001\" chat")
            }
        }
    }
}