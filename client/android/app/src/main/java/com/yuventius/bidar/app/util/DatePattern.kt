package com.yuventius.bidar.app.util

/**
 * BIDAR
 * Class: DatePattern
 * Created by Ven Choi on 2026-09-01
 */
enum class DatePattern(val pattern: String) {
    CHAT_HISTORY(pattern = "yy.MM.dd"),
    CHAT_DATE(pattern = "yyyy년 MM월 dd일"),
    CHAT_TIME(pattern = "HH:mm")
}