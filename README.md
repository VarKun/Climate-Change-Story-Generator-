# Climate Story Explorer (Buddy + Stable Diffusion)

This README documents how I run a climate change storytelling workshop for kids using the Buddy robot. Students co-create narrative chapters and illustrations in Streamlit, and a lightweight TCP server relays the results to two Android apps running on Buddy so the robot can perform the story with matching expressions.

---

## Why This Matters

- Helps children connect abstract climate concepts with characters and emotions, boosting empathy and motivation.  
- Blends text, imagery, and robot body language into an immersive classroom experience instead of static slides.  
- Gives teachers a fast way to adapt stories with local examples or discussion prompts on the fly.  
- Buddy’s facial expressions become an “emotional compass,” sparking conversations about climate anxiety and collective action.

## Learner Journey

1. **Choose a theme** – e.g., polar bears, urban tree planting, ocean cleanup.  
2. **Co-create with AI** – students craft prompts; Groq LLM writes story drafts and the Stability API renders illustrations.  
3. **Review & revise** – teacher and students tweak paragraphs, add discussion questions, and embed action items.  
4. **Send to Buddy** – the “Robot Story Teller” button pushes story text and Base64 imagery to the Python relay (`server.py`).  
5. **Robot performance** – the HelloWorld app narrates/showcases art; BuddyEmotion changes expressions based on mood cues.  
6. **Extend the story** – teams brainstorm responses to the challenges, or write the next chapter in real time.

## System Overview

```
┌────────────────────┐    prompts & edits    ┌────────────────────────┐
│ Streamlit app.py   │ ───────────────────▶ │ Groq LLM + Stability AI │
│ (Story + Image)    │ ◀────────────────────┴────────────────────────┘
└──────────┬─────────┘
           │  SAY_STORY / IMAGE_BASE64 (TCP 5058, ROLE:app)
           ▼
   ┌────────────────────┐  broadcasts to ROLE:android clients
   │ server.py (hub)    │══════════════════════════════════════════════╗
   │ routes text/image  │                                              ║
   └────────────────────┘                                              ║
           ▲                                                           ║
           │                                                           ║
┌──────────┴───────────┐      story + art        ┌─────────────────────╬────────────┐
│ HelloWorld Android   │ ◀────────────────────── │ Buddy robot display │ Story voice │
│ (image + narration)  │                         └─────────────────────╬────────────┘
└──────────▲───────────┘                                           Buddy SDK v2 speech UI
           │
           │ SAY (mood cues)
           ▼
┌──────────────────────┐
│ BuddyEmotion Android │
│ (facial expressions) │
└──────────────────────┘
```

- **Streamlit studio** – drives story writing, image generation, and classroom controls.  
- **`server.py`** – TCP hub that registers client roles, forwarding `ROLE:app` messages to all `ROLE:android` clients.  
- **HelloWorld app** – renders Base64 PNG illustrations on Buddy’s face and narrates the story aloud.  
- **BuddyEmotion app** – listens for `SAY:` messages and switches expressions based on keywords (positive / negative / undecided).

## Components

### Python Story Studio (`src/app.py`)

- Uses Groq-hosted Llama 4 models for age-appropriate climate storytelling.  
- Calls Stability AI `stable-image/generate/core` for illustrations; saves `current.png` and caches Base64 strings.  
- Logs sessions to Supabase (IDs, chat history, image descriptions) for teacher reflection.  
- `send_to_buddy` publishes `SAY_STORY:` and `IMAGE_BASE64:` lines to the relay (`BUDDY_TCP_HOST` defaults to `127.0.0.1`, port `5058`).  
- The “Robot Story Teller” button orchestrates the push to Buddy while leaving a ZeroMQ hook available for Pepper.

### Story Relay Server (`BlueFrog_SDK_examples/server.py`)

- Plain Python TCP hub: clients announce themselves as `ROLE:app` or `ROLE:android`.  
- Broadcasts app messages to all Android clients and vice versa (handy for teacher console commands).  
- Console input (`Text for Buddy> SAY:...`) is a quick way to insert prompts or mood cues mid-lesson.

### Buddy Android Apps

- **HelloWorld**  
  - Establishes a socket to the relay, identifies as `ROLE:android`.  
  - Handles `SAY_STORY:` (narration) + `IMAGE_BASE64:` (decode & display).  
  - Resets expression to neutral and hides the image once narration finishes.

- **BuddyEmotion**  
  - Listens to `SAY:` commands, parsing mood keywords to set facial expressions.  
  - Speaks the text (or a short neutral line) and updates on-screen status, acting as emotional feedback.

## Setup Checklist

1. **Environment variables**  
   ```bash
   export GROQ_API_KEY=*****
   export STABILITY_KEY=*****
   export SUPABASE_URL=*****
   export SUPABASE_KEY=*****
   export BUDDY_TCP_HOST=192.168.x.y
   export BUDDY_TCP_PORT=5058
   export IMGUR_CLIENT_ID=*****
   export BUDDY_ROBOT_IP=192.168.x.buddy      # optional test script
   export PEPPER_ROBOT_IP=192.168.x.pepper    # optional Pepper run
   ```
   Android Studio → `gradle.properties`:
   ```
   BUDDY_SOCKET_HOST=192.168.x.y
   BUDDY_SOCKET_PORT=5058
   BFR_MAVEN_USER=*****
   BFR_MAVEN_PASSWORD=*****
   ```

2. **Start the relay server**
   ```bash
   cd /Users/kunliu/BlueFrog_SDK_examples
   python server.py
   ```

3. **Launch Streamlit**
   ```bash
   cd /Users/kunliu/Buddy/ai-driven-writing-in-climate-change-Pepper
   pip install -r requirements.txt
   streamlit run src/app.py
   ```
   Click **Robot Story Teller** after generating a story/image to push them to Buddy.

4. **Deploy Buddy apps**
   - Open `HelloWorld/` and `BuddyEmotion/` in Android Studio.  
   - Ensure `BuildConfig.BUDDY_SOCKET_HOST/PORT` match the relay server (inherited from the Gradle fields above).  
   - Run both apps on Buddy; look for the “Python server connected” toast.

5. **Classroom run**
   - Iterate on the story in Streamlit; Buddy narrates in sync with illustrations.  
   - BuddyEmotion tracks mood cues (`positive`, `negative`, `undecided`) and shifts facial expressions.  
   - Optional: run `python Pepper.py --ip $PEPPER_ROBOT_IP` for a Pepper performance.

6. **Wrap-up**
   - Story text and art are stored in `current.txt` / `current.png` and per-session `logs/` directories for later review.  
   - Shut down Streamlit and the relay; remove or archive sensitive logs before publishing.

## Safety, Troubleshooting & Tips

- **Connectivity** – ensure Buddy and the Python host share the same LAN; update firewall rules if necessary.  
- **API quotas** – pre-generate a few story seeds in case Stability/Groq rate limits kick in mid-session.  
- **Content moderation** – review prompts and outputs beforehand; include phrases like “hopeful tone” or age ranges.  
- **Fallbacks** – Android clients toast on socket errors; simply tap **Robot Story Teller** again after reconnection.  
- **Hardware safety** – Buddy remains stationary; secure cables so kids can interact safely.

## Extension Ideas

- Add richer emotion cues (`SAY:JOY`, `SAY:CURIOUS`) and map them in BuddyEmotion.  
- Build a prompt library for different age groups or climate topics.  
- Blend real data (temperature logs, emissions stats) into story beats to train data literacy.  
- Add speech recognition so students can pitch ideas verbally, then use the model to continue the narrative.

## Repo Map

- `src/app.py` – Streamlit UX, story/image generation, TCP push.  
- `current.txt` / `current.png` – latest story and illustration.  
- `logs/` / `outputs/` – cached assets and session logs.  
- `BlueFrog_SDK_examples/server.py` – TCP relay.  
- `BlueFrog_SDK_examples/HelloWorld/` – narration + illustration Android app.  
- `BlueFrog_SDK_examples/BuddyEmotion/` – mood-expression Android app.

## Quick Commands

```bash
# TCP relay
python server.py             # from BlueFrog_SDK_examples/

# Story studio
streamlit run src/app.py     # from ai-driven-writing-in-climate-change-Pepper/

# Manual test broadcast
Text for Buddy> SAY:Remember to recycle your paper today!
```

## Device Mirroring (scrcpy + adb)

This repo includes a prebuilt scrcpy bundle for macOS with a local `adb` binary:

- Location: `scrcpy-macos-x86_64-v3.3.2/` (contains `scrcpy`, `adb`, `scrcpy-server`)

### Enable Developer Mode on Buddy

- On Buddy (Android), enable Developer options and turn on USB debugging.  
- When prompted, allow USB debugging from your computer.

### USB Mirroring (plug-and-play)

```bash
cd scrcpy-macos-x86_64-v3.3.2
chmod +x scrcpy adb            # one-time, if needed
./scrcpy                       # open live mirror and control Buddy
```

If macOS Gatekeeper blocks execution, run:

```bash
xattr -dr com.apple.quarantine scrcpy-macos-x86_64-v3.3.2
```

### Network (TCP/IP) Mirroring

Option A: Connect via USB once, then switch the device to TCP mode:

```bash
cd scrcpy-macos-x86_64-v3.3.2
./adb devices                  # verify Buddy is listed over USB
./adb tcpip 5555               # enable TCP on Buddy
./adb connect BUDDY_IP:5555    # replace with Buddy’s IP
./scrcpy                       # mirror over Wi‑Fi
```

Option B: Use scrcpy’s `--tcpip` convenience flag (first time may still require USB):

```bash
./scrcpy --tcpip=BUDDY_IP:5555
```

### Deploy APKs and View Logs

```bash
cd scrcpy-macos-x86_64-v3.3.2
./adb devices                      # list devices
./adb install -r /path/HelloWorld.apk
./adb install -r /path/BuddyEmotion.apk
./adb logcat | grep -Ei "HelloWorld|BuddyEmotion"   # filter app logs
```

Tip: Temporarily add the bundle to your PATH

```bash
export PATH="$PWD/scrcpy-macos-x86_64-v3.3.2:$PATH"
```

### Troubleshooting

- Device not detected: try a different USB cable/port; accept the “Allow USB debugging” prompt on Buddy.  
- Network connect fails: ensure Buddy and your Mac are on the same LAN; confirm `BUDDY_IP` and firewall rules.  
- Permission denied: ensure `chmod +x` on `scrcpy` and `adb`, or clear quarantine attributes via `xattr` above.

## Photos

Below are classroom and app screenshots stored under `photo/`:

![Buddy photo 1](photo/PHOTO-2025-10-28-13-54-14.jpg)
![WeChat image 119](photo/WechatIMG119.jpg)
![WeChat image 120](photo/WechatIMG120.jpg)
![WeChat image 121](photo/WechatIMG121.jpg)
![Streamlit screenshot](photo/Screenshot%202025-10-30%20at%2017.51.28.png)

## Step-by-Step Guide

1. Configure environment variables (`.env` or shell exports).  
2. Start `server.py` to accept Buddy connections.  
3. Run `streamlit app.py`, generate a climate story + illustration.  
4. Install and launch the HelloWorld & BuddyEmotion Android apps on Buddy.  
5. Click **Robot Story Teller**; Buddy narrates and reacts emotionally.  
6. Archive logs and clean sensitive data before sharing the project.

Bring this workflow into any theme—ocean plastics, renewable energy, city greenery—and let Buddy guide your class toward climate action! 💚🤖🌍
