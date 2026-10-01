package com.oliver.pigeonbot

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import android.widget.VideoView
import java.io.File
import java.util.Locale

class MainActivity : Activity() {
    private val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
    private val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT
    private val BG = Color.rgb(18, 18, 18)

    private val handler = Handler(Looper.getMainLooper())
    private var statusView: TextView? = null
    private var linkView: TextView? = null
    private var redButton: TextView? = null
    private var videoView: VideoView? = null
    private var playButton: TextView? = null
    private var seekBar: SeekBar? = null
    private var timeView: TextView? = null
    private var seeking = false
    private var shownStamp = 0L

    private val tick = object : Runnable {
        override fun run() { refresh(); handler.postDelayed(this, 750) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
        }
        showScreen()
    }

    override fun onResume() { super.onResume(); handler.post(tick) }
    override fun onPause() { super.onPause(); handler.removeCallbacks(tick) }
    override fun onNewIntent(intent: Intent?) { super.onNewIntent(intent); refresh() }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

    private fun label(s: String, size: Float, bold: Boolean) = TextView(this).apply {
        text = s
        textSize = size
        setTextColor(Color.WHITE)
        if (bold) typeface = Typeface.DEFAULT_BOLD
        setPadding(0, dp(6), 0, dp(6))
    }

    private fun showScreen() {
        shownStamp = 0L
        statusView = null; linkView = null; redButton = null; videoView = null
        playButton = null; seekBar = null; timeView = null
        if (Store.token(this).isEmpty()) tokenScreen() else mainScreen()
    }

    private fun tokenScreen() {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(48), dp(24), dp(24))
        }
        col.addView(label("Connect to GitHub", 24f, true))
        col.addView(label(
            "The app needs a GitHub token to start your pigeon bot.\n\n" +
            "1. Tap the button below and sign in to GitHub\n" +
            "2. Token name: pigeon app. Expiration: the longest option\n" +
            "3. Repository access: Only select repositories -> pigeon-bot\n" +
            "4. Permissions -> Repository permissions -> Actions: Read and write\n" +
            "5. Generate token, copy it, and paste it below", 15f, false))
        col.addView(Button(this).apply {
            text = "Open GitHub token page"
            setOnClickListener {
                startActivity(Intent(Intent.ACTION_VIEW,
                    Uri.parse("https://github.com/settings/personal-access-tokens/new")))
            }
        })
        val input = EditText(this).apply {
            setHint("github_pat_...")
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        col.addView(input)
        col.addView(Button(this).apply {
            text = "Save"
            setOnClickListener {
                val t = input.text.toString().trim()
                if (t.length < 20) toast("That doesn't look like a GitHub token")
                else { Store.setToken(this@MainActivity, t); showScreen() }
            }
        })
        setContentView(ScrollView(this).apply { setBackgroundColor(BG); addView(col) })
    }

    private fun mainScreen() {
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(16), dp(40), dp(16), dp(16))
            setBackgroundColor(BG)
        }
        col.addView(label("Pigeon Bot", 26f, true))

        val size = dp(200)
        val btn = TextView(this).apply {
            text = "MAKE\nVIDEO"
            textSize = 28f
            setTextColor(Color.WHITE)
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.rgb(220, 20, 30))
                setStroke(dp(6), Color.rgb(120, 0, 0))
            }
            elevation = dp(8).toFloat()
            isClickable = true
            setOnClickListener { startBot() }
        }
        col.addView(btn, LinearLayout.LayoutParams(size, size).apply {
            topMargin = dp(12); bottomMargin = dp(12)
        })

        val st = label("", 16f, false).apply { gravity = Gravity.CENTER }
        col.addView(st, LinearLayout.LayoutParams(MATCH, WRAP))

        val link = label("", 14f, false).apply {
            setTextColor(Color.rgb(120, 170, 255))
            gravity = Gravity.CENTER
            setOnClickListener {
                val u = Store.runUrl(this@MainActivity)
                if (u.isNotEmpty()) startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(u)))
            }
        }
        col.addView(link, LinearLayout.LayoutParams(MATCH, WRAP))

        val frame = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        val vv = VideoView(this)
        frame.addView(vv, FrameLayout.LayoutParams(MATCH, MATCH, Gravity.CENTER))
        col.addView(frame, LinearLayout.LayoutParams(MATCH, 0, 1f).apply { topMargin = dp(8) })
        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(4), dp(8), dp(4))
            background = GradientDrawable().apply {
                setColor(Color.rgb(35, 35, 35))
                cornerRadius = dp(12).toFloat()
            }
        }
        val play = TextView(this).apply {
            text = "▶"
            textSize = 26f
            gravity = Gravity.CENTER
            setTextColor(Color.WHITE)
            contentDescription = "Play or pause video"
            setOnClickListener {
                if (vv.isPlaying) vv.pause() else vv.start()
                updatePlayerControls()
            }
        }
        controls.addView(play, LinearLayout.LayoutParams(dp(48), dp(48)))
        val seek = SeekBar(this).apply {
            max = 1000
            progressTintList = android.content.res.ColorStateList.valueOf(Color.rgb(255, 81, 93))
            thumbTintList = android.content.res.ColorStateList.valueOf(Color.rgb(255, 81, 93))
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onStartTrackingTouch(bar: SeekBar) { seeking = true }
                override fun onStopTrackingTouch(bar: SeekBar) { seeking = false; updatePlayerControls() }
                override fun onProgressChanged(bar: SeekBar, progress: Int, fromUser: Boolean) {
                    if (fromUser && vv.duration > 0) {
                        vv.seekTo((vv.duration.toLong() * progress / 1000).toInt())
                        updatePlayerControls()
                    }
                }
            })
        }
        controls.addView(seek, LinearLayout.LayoutParams(0, dp(48), 1f))
        val time = TextView(this).apply {
            text = "0:00 / 0:00"
            textSize = 12f
            setTextColor(Color.LTGRAY)
            gravity = Gravity.CENTER_END
            setSingleLine(true)
        }
        controls.addView(time, LinearLayout.LayoutParams(dp(88), dp(48)))
        col.addView(controls, LinearLayout.LayoutParams(MATCH, WRAP).apply { topMargin = dp(8) })
        vv.setOnPreparedListener { mp -> mp.isLooping = true; vv.start(); updatePlayerControls() }
        vv.setOnErrorListener { _, _, _ -> st.text = "Couldn't play the video file."; true }

        col.addView(label("Change GitHub token", 13f, false).apply {
            setTextColor(Color.GRAY)
            gravity = Gravity.CENTER
            setOnClickListener { Store.setToken(this@MainActivity, ""); showScreen() }
        }, LinearLayout.LayoutParams(MATCH, WRAP))

        setContentView(col)
        statusView = st; linkView = link; redButton = btn; videoView = vv
        playButton = play; seekBar = seek; timeView = time
        refresh()
    }

    private fun formatTime(ms: Int): String =
        String.format(Locale.US, "%d:%02d", ms / 60000, (ms / 1000) % 60)

    private fun updatePlayerControls() {
        val vv = videoView ?: return
        val duration = vv.duration.coerceAtLeast(0)
        val position = vv.currentPosition.coerceAtLeast(0)
        playButton?.text = if (vv.isPlaying) "Ⅱ" else "▶"
        if (!seeking) seekBar?.progress = if (duration > 0) (position.toLong() * 1000 / duration).toInt() else 0
        timeView?.text = "${formatTime(position)} / ${formatTime(duration)}"
    }

    private fun refresh() {
        val st = statusView ?: return
        val busy = Store.busy(this)
        st.text = Store.status(this)
        redButton?.alpha = if (busy) 0.4f else 1f
        linkView?.text = if (Store.runUrl(this).isNotEmpty()) "Open run on GitHub" else ""
        val f = File(filesDir, "latest.mp4")
        if (f.exists() && f.length() > 0 && f.lastModified() != shownStamp) {
            shownStamp = f.lastModified()
            videoView?.setVideoPath(f.absolutePath)
        }
        updatePlayerControls()
    }

    private fun startBot() {
        if (Store.busy(this)) { toast("Already making a video - hang on"); return }
        Store.setRunUrl(this, "")
        Store.setStatus(this, "Starting...")
        Store.setRunning(this, true)
        Store.beat(this)
        startForegroundService(Intent(this, PigeonService::class.java))
        refresh()
    }
}
