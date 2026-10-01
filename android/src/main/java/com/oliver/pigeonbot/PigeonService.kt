package com.oliver.pigeonbot

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import org.json.JSONObject
import java.io.File
import java.util.UUID

class PigeonService : Service() {
    @Volatile private var working = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        channels()
        val n = progress("Starting...")
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(1, n)
        }
        if (!working) {
            working = true
            Store.setRunning(this, true)
            Store.beat(this)
            Thread {
                try {
                    work()
                } catch (e: Exception) {
                    done("Pigeon bot failed", "Something went wrong: ${e.message}")
                } finally {
                    working = false
                    Store.setRunning(this, false)
                    stopForeground(Service.STOP_FOREGROUND_REMOVE)
                    stopSelf()
                }
            }.start()
        }
        return START_NOT_STICKY
    }

    private fun work() {
        val token = Store.token(this)
        if (token.isEmpty()) throw Exception("No GitHub token saved")
        val gh = GitHub(token)
        val rid = UUID.randomUUID().toString().replace("-", "").take(10)

        update("Asking GitHub to start the bot...")
        gh.dispatch(rid)

        update("Waiting for GitHub to start...")
        var run: JSONObject? = null
        for (i in 0 until 36) {
            Thread.sleep(5000)
            run = gh.findRun(rid)
            if (run != null) break
            Store.beat(this)
        }
        if (run == null) throw Exception("GitHub didn't start the run. Check the Actions tab.")
        val id = run.getLong("id")
        Store.setRunUrl(this, run.optString("html_url"))

        val t0 = System.currentTimeMillis()
        var conclusion = ""
        while (true) {
            val r = gh.run(id)
            val status = r.optString("status")
            if (status == "completed") { conclusion = r.optString("conclusion"); break }
            val mins = (System.currentTimeMillis() - t0) / 60000
            if (mins > 55) throw Exception("It's taking too long. Check the run on GitHub.")
            update(if (status == "in_progress") "Making your pigeon video... ($mins min)"
                   else "Waiting in line on GitHub... ($mins min)")
            Thread.sleep(20000)
        }

        update("Downloading the video...")
        val got = gh.downloadVideo(id, File(filesDir, "latest.mp4"))
        when {
            got && conclusion == "success" ->
                done("Pigeon video ready!", "Done! Your pigeon video is ready to download.")
            got ->
                done("Pigeon video ready!", "Your pigeon video is ready. Tap 'Open run on GitHub' for details.")
            else ->
                done("Pigeon bot failed", "No video was made (run $conclusion). Tap 'Open run on GitHub' to see why.")
        }
    }

    private fun openApp(): PendingIntent {
        val i = Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        return PendingIntent.getActivity(this, 0, i,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    private fun channels() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("progress", "Making video", NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel("done", "Video ready", NotificationManager.IMPORTANCE_HIGH))
    }

    private fun progress(msg: String): Notification =
        Notification.Builder(this, "progress")
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle("Pigeon Bot")
            .setContentText(msg)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openApp())
            .build()

    private fun update(msg: String) {
        Store.setStatus(this, msg)
        Store.beat(this)
        getSystemService(NotificationManager::class.java).notify(1, progress(msg))
    }

    private fun done(title: String, msg: String) {
        Store.setStatus(this, msg)
        val n = Notification.Builder(this, "done")
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle(title)
            .setContentText(msg)
            .setStyle(Notification.BigTextStyle().bigText(msg))
            .setContentIntent(openApp())
            .setAutoCancel(true)
            .build()
        getSystemService(NotificationManager::class.java).notify(2, n)
    }
}
