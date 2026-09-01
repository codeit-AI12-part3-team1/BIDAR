package com.yuventius.bidar.app.di

import android.content.Context
import androidx.room.Room
import com.yuventius.bidar.data.local.AppDatabase
import com.yuventius.bidar.data.local.ChatDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * BIDAR
 * Class: DatabaseModule
 * Created by Ven Choi on 2026-09-01
 */
@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    private const val DATABASE_NAME = "bidar.db"

    @Provides
    @Singleton
    fun provideAppDatabase(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, DATABASE_NAME)
            .build()

    @Provides
    @Singleton
    fun provideChatDao(appDatabase: AppDatabase): ChatDao = appDatabase.chatDao()
}
