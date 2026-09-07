package com.yuventius.bidar.app.ui.view.screen.splash

import androidx.lifecycle.ViewModel
import com.yuventius.bidar.app.ui.view.screen.splash.state.SplashSideEffect
import com.yuventius.bidar.app.ui.view.screen.splash.state.SplashState
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import org.orbitmvi.orbit.OrbitContainerHost
import org.orbitmvi.orbit.viewmodel.orbitContainer
import javax.inject.Inject
import kotlin.time.Duration.Companion.milliseconds

/**
 * BIDAR
 * Class: SplashVM
 * Created by Ven Choi on 2026-09-01
 */
private const val SPLASH_DURATION_MILLIS = 3000L

@HiltViewModel
class SplashVM @Inject constructor() : OrbitContainerHost<SplashState, SplashState, SplashSideEffect>, ViewModel() {
    override val container = orbitContainer<SplashState, SplashSideEffect>(SplashState()) {
        delay(SPLASH_DURATION_MILLIS.milliseconds)
        postSideEffect(SplashSideEffect.MoveToHome)
    }
}
