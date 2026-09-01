package com.yuventius.bidar.app.navigation

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.yuventius.bidar.app.ui.view.screen.chat.ChatView
import com.yuventius.bidar.app.ui.view.screen.home.HomeView
import com.yuventius.bidar.app.ui.view.screen.splash.SplashView

/**
 * BIDAR
 * Class: BidarNavHost
 * Created by Ven Choi on 2026-09-01
 */
@Composable
fun BidarNavHost(
    modifier: Modifier = Modifier,
    navController: NavHostController = rememberNavController()
) {
    NavHost(
        navController = navController,
        startDestination = Route.Splash.route,
        modifier = modifier
    ) {
        composable(
            route = Route.Splash.route,
            exitTransition = { fadeOut() }
        ) {
            SplashView(
                onNavigateToHome = {
                    // splash를 백스택에서 제거 -> home에서 뒤로가기 시 splash로 돌아가지 않고 앱 종료
                    navController.navigate(Route.Home.route) {
                        popUpTo(Route.Splash.route) { inclusive = true }
                    }
                }
            )
        }
        composable(
            route = Route.Home.route,
            enterTransition = { fadeIn() },
            exitTransition = { slideOutOfContainer(AnimatedContentTransitionScope.SlideDirection.Left) },
            popEnterTransition = { slideIntoContainer(AnimatedContentTransitionScope.SlideDirection.Right) }
        ) {
            HomeView (
                onNavigateToChat = { documentId ->
                    navController.navigate(Route.Chat.createRoute(documentId))
                }
            )
        }
        composable(
            route = Route.Chat.route,
            arguments = listOf(navArgument(Route.Chat.ARG_DOCUMENT_ID) { type = NavType.StringType }),
            enterTransition = { slideIntoContainer(AnimatedContentTransitionScope.SlideDirection.Left) },
            popExitTransition = { slideOutOfContainer(AnimatedContentTransitionScope.SlideDirection.Right) }
        ) { backStackEntry ->
            val documentId = backStackEntry.arguments?.getString(Route.Chat.ARG_DOCUMENT_ID).orEmpty()
            ChatView(
                documentId = documentId,
                onNavigateBack = { navController.popBackStack() }
            )
        }
    }
}
