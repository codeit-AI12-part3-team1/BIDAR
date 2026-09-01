package com.yuventius.bidar.data.local

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
        WHERE documentId = :documentId ORDER BY id ASC
    """)
    fun getChats(documentId: String): Flow<List<ChatLocal>>

    @Query("""
        SELECT chatDate
        FROM chat
        WHERE documentId = :documentId ORDER BY id DESC LIMIT 1
    """)
    fun getLastChatDate(documentId: String): Flow<String?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(chat: ChatLocal): Long

    @Delete
    suspend fun delete(chat: ChatLocal)
}
