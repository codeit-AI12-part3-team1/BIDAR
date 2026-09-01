package com.yuventius.bidar.app.core

import android.app.Application
import com.orhanobut.logger.AndroidLogAdapter
import com.orhanobut.logger.Logger
import dagger.hilt.android.HiltAndroidApp

/**
 * BIDAR
 * Class: App
 * Created by Ven Choi on 2026-09-01
 */
@HiltAndroidApp
class App: Application() {
    override fun onCreate() {
        super.onCreate()
        Logger.addLogAdapter(AndroidLogAdapter())
    }
}