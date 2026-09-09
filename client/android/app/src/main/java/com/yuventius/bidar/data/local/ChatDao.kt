package com.yuventius.bidar.data.local

import androidx.paging.PagingSource
import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.yuventius.bidar.data.local.model.ChatLocal
import kotlinx.coroutines.flow.Flow

/**
 * BIDAR
 * Class: ChatDao
 * Created by Ven Choi on 2026-09-01
 */
@Dao
interface ChatDao {
    @Query("""
        SELECT *
        FROM chat
        WHERE documentId = :documentId ORDER BY id DESC
    """)
    fun getChats(documentId: String): PagingSource<Int, ChatLocal>

    @Query("""
        SELECT chatDate
        FROM chat
        WHERE documentId = :documentId ORDER BY id DESC LIMIT 1
    """)
    fun getLastChatDate(documentId: String): Flow<String?>

    @Query("SELECT COUNT(*) FROM chat WHERE documentId = :documentId")
    suspend fun getChatCount(documentId: String): Int

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(chat: ChatLocal): Long

    @Delete
    suspend fun delete(chat: ChatLocal)

    @Query("DELETE FROM chat")
    suspend fun deleteAll()
}
