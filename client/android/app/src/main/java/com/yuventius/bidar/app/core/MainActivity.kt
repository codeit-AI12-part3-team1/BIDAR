package com.yuventius.bidar.app.core

import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
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
        // 앱이 라이트 테마만 사용하므로 시스템 다크모드와 무관하게 상태바/내비게이션바 아이콘을 어둡게 고정
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
        )
        setContent {
            BIDARTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    BidarNavHost(modifier = Modifier.padding(innerPadding))
                }
            }
        }
    }
}