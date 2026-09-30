package com.oliver.pigeonbot

import android.content.Context

object Store {
    private fun p(c: Context) = c.getSharedPreferences("pigeon", Context.MODE_PRIVATE)

    fun token(c: Context): String = p(c).getString("token", "") ?: ""
    fun setToken(c: Context, v: String) = p(c).edit().putString("token", v).apply()

    fun status(c: Context): String = p(c).getString("status",
        "Press the big red button to make a pigeon video from a random Zach D Films TikTok.") ?: ""
    fun setStatus(c: Context, v: String) = p(c).edit().putString("status", v).apply()

    fun runUrl(c: Context): String = p(c).getString("runUrl", "") ?: ""
    fun setRunUrl(c: Context, v: String) = p(c).edit().putString("runUrl", v).apply()

    fun setRunning(c: Context, v: Boolean) = p(c).edit().putBoolean("running", v).apply()
    fun beat(c: Context) = p(c).edit().putLong("beat", System.currentTimeMillis()).apply()

    fun busy(c: Context): Boolean =
        p(c).getBoolean("running", false) &&
            System.currentTimeMillis() - p(c).getLong("beat", 0L) < 180_000L
}