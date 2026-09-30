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
import android.widget.MediaController
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import android.widget.VideoView
import java.io.File

class MainActivity : Activity() {
    private val MATCH = ViewGroup.LayoutParams.MATCH_PARENT
    private val WRAP = ViewGroup.LayoutParams.WRAP_CONTENT
    private val BG = Color.rgb(18, 18, 18)

    private val handler = Handler(Looper.getMainLooper())
    private var statusView: TextView? = null
    private var linkView: TextView? = null
    private var redButton: TextView? = null
    private var videoView: VideoView? = null
    private var shownStamp = 0L

    private val tick = object : Runnable {
        override fun run() { refresh(); handler.postDelayed(this, 1500) }
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

        val frame = FrameLayout(this)
        val vv = VideoView(this)
        frame.addView(vv, FrameLayout.LayoutParams(WRAP, WRAP, Gravity.CENTER))
        col.addView(frame, LinearLayout.LayoutParams(MATCH, 0, 1f).apply { topMargin = dp(8) })
        val mc = MediaController(this)
        mc.setAnchorView(vv)
        vv.setMediaController(mc)
        vv.setOnPreparedListener { mp -> mp.isLooping = true; vv.start() }
        vv.setOnErrorListener { _, _, _ -> st.text = "Couldn't play the video file."; true }

        col.addView(label("Change GitHub token", 13f, false).apply {
            setTextColor(Color.GRAY)
            gravity = Gravity.CENTER
            setOnClickListener { Store.setToken(this@MainActivity, ""); showScreen() }
        }, LinearLayout.LayoutParams(MATCH, WRAP))

        setContentView(col)
        statusView = st; linkView = link; redButton = btn; videoView = vv
        refresh()
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