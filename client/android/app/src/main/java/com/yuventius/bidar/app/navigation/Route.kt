package com.yuventius.bidar.app.navigation

import android.net.Uri
import com.yuventius.bidar.domain.model.Document

/**
 * BIDAR
 * Class: Route
 * Created by Ven Choi on 2026-09-01
 */
sealed class Route(val route: String) {
    data object Splash: Route("splash")
    data object Home: Route("home")
    data object Chat: Route("chat/{documentId}/{documentTitle}") {
        const val ARG_DOCUMENT_ID = "documentId"
        const val ARG_DOCUMENT_TITLE = "documentTitle"
        fun createRoute(document: Document) =
            "chat/${Uri.encode(document.documentId)}/${Uri.encode(document.title)}"
    }

    data object Setting: Route("setting")
}
