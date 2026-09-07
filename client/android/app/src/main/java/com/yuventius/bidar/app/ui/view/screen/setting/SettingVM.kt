package com.yuventius.bidar.app.ui.view.screen.setting

import androidx.lifecycle.ViewModel
import com.yuventius.bidar.domain.repository.ChatRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.StateFlow
import org.orbitmvi.orbit.OrbitContainer
import org.orbitmvi.orbit.OrbitContainerHost
import org.orbitmvi.orbit.viewmodel.orbitContainer
import javax.inject.Inject

/**
 * BIDAR
 * Class: SettingVM
 * Created by Ven Choi on 2026-09-07
 */
@HiltViewModel
class SettingVM @Inject constructor (
    private val chatRepository: ChatRepository
): OrbitContainerHost<Any, Any, Any>, ViewModel() {
    override val container = orbitContainer(Any())

    val useStreaming: StateFlow<Boolean> = chatRepository.useStreaming
    val useOpenAi: StateFlow<Boolean> = chatRepository.useOpenAi

    fun clearAllChats() = intent {
        chatRepository.deleteAll()
    }

    fun setUseStreaming(enabled: Boolean) {
        chatRepository.setUseStreaming(enabled)
    }

    fun setUseOpenAi(enabled: Boolean) {
        chatRepository.setUseOpenAi(enabled)
    }
}