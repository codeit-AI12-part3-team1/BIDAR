package com.yuventius.bidar.app.ui.view.screen.splash

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.lifecycle.viewmodel.compose.hiltViewModel
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

    Box (
        modifier = modifier
            .fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Text("SPLASH VIEW")
    }
}