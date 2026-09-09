package com.yuventius.bidar.app.util

import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * BIDAR
 * Class: LocalDateTimeExt
 * Created by Ven Choi on 2026-09-01
 */
fun LocalDateTime.formatByDatePattern(datePattern: DatePattern): String {
    val formatter = DateTimeFormatter.ofPattern(datePattern.pattern)
    return this.format(formatter)
}