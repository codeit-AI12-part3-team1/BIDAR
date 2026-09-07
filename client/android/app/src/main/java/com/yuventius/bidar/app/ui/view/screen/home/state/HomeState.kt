package com.yuventius.bidar.app.ui.view.screen.home.state

import com.yuventius.bidar.domain.model.Document

/**
 * BIDAR
 * Class: HomeState
 * Created by Ven Choi on 2026-09-07
 */
data class HomeState (
    val status: HomeStatus = HomeStatus.LOADING,
    val documents: List<Document> = emptyList()
)