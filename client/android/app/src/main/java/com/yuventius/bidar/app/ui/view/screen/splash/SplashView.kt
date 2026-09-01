package com.yuventius.bidar.app.ui.view.screen.splash

import android.content.Context
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
import com.yuventius.bidar.R
import com.yuventius.bidar.app.ui.theme.BIDARTheme
import com.yuventius.bidar.app.ui.theme.MidnightIndigo
import com.yuventius.bidar.app.ui.theme.White40
import com.yuventius.bidar.app.ui.view.screen.splash.state.SplashSideEffect
import org.orbitmvi.orbit.compose.collectSideEffect

/**
 * BIDAR
 * Class: SplashView
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun SplashView (
    modifier: Modifier = Modifier,
    viewModel: SplashVM = hiltViewModel(),
    onNavigateToHome: () -> Unit = {}
) {
    viewModel.collectSideEffect { sideEffect ->
        when (sideEffect) {
            SplashSideEffect.MoveToHome -> onNavigateToHome()
        }
    }

    SplashContent(modifier = modifier)
}

@Composable
private fun SplashContent(
    modifier: Modifier = Modifier
) {
    Box (
        modifier = modifier
            .fillMaxSize()
            .background(MidnightIndigo),
        contentAlignment = Alignment.Center
    ) {
        Column (
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Image(
                painter = painterResource(R.drawable.ic_logo_outlined),
                contentDescription = null
            )
            Text(
                text = "AI 기반 RFP 분석 챗봇",
                fontSize = 12.sp,
                color = White40
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun SplashContentPreview() {
    BIDARTheme {
        SplashContent()
    }
}