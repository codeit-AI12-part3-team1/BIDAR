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
            // TODO: 정식 마이그레이션 전략 도입 전까지, 개발 단계 스키마 변경 시 로컬 채팅 캐시를 초기화
            .fallbackToDestructiveMigration(dropAllTables = true)
            .build()

    @Provides
    @Singleton
    fun provideChatDao(appDatabase: AppDatabase): ChatDao = appDatabase.chatDao()
}
