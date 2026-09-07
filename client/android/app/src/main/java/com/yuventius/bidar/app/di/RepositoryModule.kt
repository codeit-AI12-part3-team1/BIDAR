package com.yuventius.bidar.app.di

import com.yuventius.bidar.data.local.repository.ChatRepositoryImpl
import com.yuventius.bidar.data.remote.repository.DocumentRepositoryImpl
import com.yuventius.bidar.domain.repository.ChatRepository
import com.yuventius.bidar.domain.repository.DocumentRepository
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * BIDAR
 * Class: RepositoryModule
 * Created by Ven Choi on 2026-09-01
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds
    @Singleton
    abstract fun bindDocumentRepository(impl: DocumentRepositoryImpl): DocumentRepository

    @Binds
    @Singleton
    abstract fun bindChatRepository(impl: ChatRepositoryImpl): ChatRepository
}
