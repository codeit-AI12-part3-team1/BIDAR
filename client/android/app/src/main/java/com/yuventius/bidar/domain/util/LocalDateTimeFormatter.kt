package com.yuventius.bidar.domain.util

import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * BIDAR
 * Class: LocalDateTimeFormatter
 * Created by Ven Choi on 2026-09-01
 */
object LocalDateTimeFormatter {
    fun toLocalDateTime(timeString: String): LocalDateTime {
        val formatter: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
        return LocalDateTime.parse(timeString, formatter)
    }

    fun toTimeString(localDateTime: LocalDateTime): String {
        val formatter: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
        return localDateTime.format(formatter)
    }
}