package com.oliver.pigeonbot

import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.ZipInputStream

const val REPO = "youtubeai2012/pigeon-bot"

class GitHub(private val token: String) {
    private val base = "https://api.github.com/repos/$REPO"

    private fun open(url: String, method: String = "GET", auth: Boolean = true): HttpURLConnection {
        val c = URL(url).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 20000
        c.readTimeout = 120000
        c.instanceFollowRedirects = false
        c.setRequestProperty("User-Agent", "pigeon-bot-app")
        if (auth) {
            c.setRequestProperty("Accept", "application/vnd.github+json")
            c.setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
            c.setRequestProperty("Authorization", "Bearer $token")
        }
        return c
    }

    private fun errorText(c: HttpURLConnection, code: Int): String {
        val body = try { c.errorStream?.bufferedReader()?.use { it.readText() } } catch (e: Exception) { null }
        val msg = try { JSONObject(body ?: "").optString("message") } catch (e: Exception) { body ?: "" }
        return when (code) {
            401 -> "Your GitHub token is wrong or expired. Tap 'Change GitHub token'."
            403 -> "Your GitHub token doesn't have permission ($msg). It needs Actions: Read and write."
            404 -> "GitHub says not found. Make sure the token has access to pigeon-bot."
            else -> "GitHub error $code: $msg"
        }
    }

    private fun getJson(url: String): JSONObject {
        val c = open(url)
        val code = c.responseCode
        if (code != 200) throw Exception(errorText(c, code))
        return JSONObject(c.inputStream.bufferedReader().use { it.readText() })
    }

    fun dispatch(requestId: String) {
        val c = open("$base/actions/workflows/pigeon.yml/dispatches", "POST")
        c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        val body = JSONObject()
            .put("ref", "main")
            .put("inputs", JSONObject().put("mode", "random").put("post", "yes").put("request_id", requestId))
        c.outputStream.use { it.write(body.toString().toByteArray()) }
        val code = c.responseCode
        if (code !in 200..299) throw Exception(errorText(c, code))
    }

    fun findRun(requestId: String): JSONObject? {
        val runs = getJson("$base/actions/workflows/pigeon.yml/runs?event=workflow_dispatch&per_page=20")
            .getJSONArray("workflow_runs")
        for (i in 0 until runs.length()) {
            val r = runs.getJSONObject(i)
            if (r.optString("display_title").contains(requestId)) return r
        }
        return null
    }

    fun run(id: Long): JSONObject = getJson("$base/actions/runs/$id")

    fun downloadVideo(id: Long, dest: File): Boolean {
        repeat(6) {
            val arts = getJson("$base/actions/runs/$id/artifacts").getJSONArray("artifacts")
            for (i in 0 until arts.length()) {
                val a = arts.getJSONObject(i)
                if (a.optString("name") == "pigeon-video" && !a.optBoolean("expired")) {
                    unzipMp4(a.getString("archive_download_url"), dest)
                    return true
                }
            }
            Thread.sleep(5000)
        }
        return false
    }

    private fun unzipMp4(url: String, dest: File) {
        var c = open(url)
        var code = c.responseCode
        if (code in 300..399) {
            val loc = c.getHeaderField("Location")
            c.disconnect()
            c = open(loc, auth = false)
            code = c.responseCode
        }
        if (code != 200) throw Exception(errorText(c, code))
        val tmp = File(dest.parentFile, "download.tmp")
        ZipInputStream(c.inputStream.buffered()).use { zip ->
            var e = zip.nextEntry
            while (e != null) {
                if (!e.isDirectory && e.name.endsWith(".mp4")) {
                    tmp.outputStream().use { zip.copyTo(it) }
                    if (!tmp.renameTo(dest)) { dest.delete(); tmp.renameTo(dest) }
                    return
                }
                e = zip.nextEntry
            }
        }
        throw Exception("The download didn't contain an mp4")
    }
}
