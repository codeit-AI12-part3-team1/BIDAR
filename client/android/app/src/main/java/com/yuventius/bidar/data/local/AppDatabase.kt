package com.yuventius.bidar.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import com.yuventius.bidar.data.local.model.ChatLocal

/**
 * BIDAR
 * Class: AppDatabase
 * Created by Ven Choi on 2026-09-01
 */
@Database(entities = [ChatLocal::class], version = 1, exportSchema = false)
abstract class AppDatabase : RoomDatabase() {
    abstract fun chatDao(): ChatDao
}
