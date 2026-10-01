# Connect the pigeon bot to YouTube

The YouTube channel name, picture, and bio do not authorize an automated upload. The bot needs a Google Cloud OAuth client for the channel owner.

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable **YouTube Data API v3**.
2. Under **Google Auth Platform**, configure the consent screen for an external app. Add your Google account as a test user while setting it up.
3. Under **Clients**, create an OAuth client of type **Desktop app** and download its JSON file. Keep this file private; never commit it to GitHub.
4. On this computer, from the `pigeon-bot` folder, run:

   ```powershell
   python -m pip install -r youtube-setup-requirements.txt
   python youtube_connect.py "C:\path\to\client_secret.json"
   ```

5. Open the URL printed by the helper in the browser signed into the correct YouTube channel, approve the upload permission, and wait for the helper to save `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` to GitHub Actions secrets. It does not print these secrets.

After that, scheduled runs and the app button upload the same finished video to TikTok and YouTube. The bot asks YouTube for public visibility, reports the resulting visibility in `youtube_status.json` in the run's debug artifact, and keeps TikTok posting independent if YouTube fails.

**Public upload restriction:** [YouTube's `videos.insert` documentation](https://developers.google.com/youtube/v3/docs/videos/insert) says uploads from unverified API projects created after 28 July 2020 are forced to **private** until the project passes a [YouTube API compliance audit](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits). This audit is required for unattended public posting through the official API.

**Permanent authorization:** Google's [OAuth documentation](https://developers.google.com/identity/protocols/oauth2) says an external consent screen left in **Testing** issues refresh tokens that expire after seven days for this upload scope. Move the consent screen to **In production** for long-term automation; Google may require verification.

YouTube classifies eligible vertical videos up to three minutes as Shorts; see [YouTube's Shorts upload guidance](https://support.google.com/youtube/answer/12921536).
