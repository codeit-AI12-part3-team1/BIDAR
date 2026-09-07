package com.yuventius.bidar.app.ui.view.screen.home

import androidx.lifecycle.ViewModel
import com.yuventius.bidar.app.ui.view.screen.home.state.HomeSideEffect
import com.yuventius.bidar.app.ui.view.screen.home.state.HomeState
import com.yuventius.bidar.app.ui.view.screen.home.state.HomeStatus
import com.yuventius.bidar.domain.repository.DocumentRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import org.orbitmvi.orbit.OrbitContainer
import org.orbitmvi.orbit.OrbitContainerHost
import org.orbitmvi.orbit.viewmodel.orbitContainer
import javax.inject.Inject
import kotlin.time.Duration.Companion.milliseconds

/**
 * BIDAR
 * Class: HomeVM
 * Created by Ven Choi on 2026-09-01
 */
@HiltViewModel
class HomeVM @Inject constructor (
    val documentRepos: DocumentRepository
): OrbitContainerHost<HomeState, HomeState, HomeSideEffect>, ViewModel() {
    override val container = orbitContainer<HomeState, HomeSideEffect>(HomeState()) {
        getDocuments()
    }

    fun getDocuments() = intent {
        val result = documentRepos.getDocuments()
        reduce {
            state.copy (
                status = HomeStatus.LOADED,
                documents = result
            )
        }
    }

    fun refreshDocuments() = intent {
        reduce {
            state.copy (
                status = HomeStatus.LOADING
            )
        }
        delay(500L.milliseconds)
        getDocuments()
    }
}