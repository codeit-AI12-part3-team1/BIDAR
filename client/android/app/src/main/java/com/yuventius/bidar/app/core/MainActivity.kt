package com.yuventius.bidar.app.core

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.ui.Modifier
import com.yuventius.bidar.app.navigation.BidarNavHost
import com.yuventius.bidar.app.ui.theme.BIDARTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            BIDARTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    BidarNavHost(modifier = Modifier.padding(innerPadding))
                }
            }
        }
    }
}