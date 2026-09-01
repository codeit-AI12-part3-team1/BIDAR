package com.yuventius.bidar.app.navigation

/**
 * BIDAR
 * Class: Route
 * Created by Ven Choi on 2026-09-01
 */
sealed class Route(val route: String) {
    data object Splash : Route("splash")
    data object Home : Route("home")
    data object Chat : Route("chat/{documentId}") {
        const val ARG_DOCUMENT_ID = "documentId"
        fun createRoute(documentId: String) = "chat/$documentId"
    }
}
