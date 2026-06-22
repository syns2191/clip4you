# storyhero-mvp

A minimal, working clone of the StoryHero pipeline: feed it a long video
(stream VOD, podcast, YouTube video) and it transcribes it, asks an LLM to
find the clip-worthy moments, then cuts, reframes to vertical, and burns
in animated word-by-word captions plus a text hook — fully automatically.

It also has a **story mode** that creates narrated short videos from a script
with AI-generated illustrations, per-scene mood/voice control, and automatic
YouTube Shorts upload.

This is the *engine*, not the SaaS. No web UI, no auth, no billing, no
queue — just the core pipeline running as a CLI script.

## How it works

1. **`src/transcribe.py`** — transcribes audio to word-level timestamps (Groq cloud or local faster-whisper).
2. **`src/clip_selector.py`** — feeds the timestamped transcript to an LLM in ~20-minute windows to identify clip-worthy moments with title, hook text, category, and virality score.
3. **`src/render.py`** — uses `ffmpeg` to cut, reframe to 9:16 vertical, and composite effects.
4. **`src/captions.py`** — builds `.ass` subtitles with karaoke-style word highlighting.
5. **`src/imagegen.py`** — AI image generation for story scenes (OpenAI or Stable Diffusion).
6. **`src/upload.py`** — automatic YouTube Shorts upload with LLM-optimized metadata.
7. **`src/main.py`** — orchestrates everything and writes finished `.mp4` files.

## Setup

```bash
pip install -r requirements.txt
brew install homebrew-ffmpeg/ffmpeg/ffmpeg --with-ffprobe-full   # macOS (full build with all codecs)
cp .env.example .env  # then add your API keys
```

---

## Clip Mode — Extract clips from long videos

### Basic usage

```bash
# Process a local video, extract 5 clips
python -m src.main --input video.mp4

# Process from YouTube (downloads in HD up to 1080p)
python -m src.main --youtube-url "https://youtube.com/watch?v=..." --num-clips 3
```

### All flags (clip mode)

| Flag | Description | Default |
|------|-------------|---------|
| `--input FILE` | Path to local source video | — |
| `--youtube-url URL` | YouTube URL to download (HD 1080p) | — |
| `--num-clips N` | Number of clips to find | 5 |
| `--output-dir DIR` | Output directory | `./output` |
| `--start SECONDS` | Trim source from this time | — |
| `--end SECONDS` | Trim source until this time | — |
| `--reframe {crop,blur}` | Vertical reframing mode | `crop` |
| `--emoji` | Add emoji pop-in at punchline | off |
| `--prompt TEXT` | Custom guidance for clip selection | — |
| `--interactive` / `-i` | Pick which clips to render | off |
| `--max-duration SEC` | Max clip duration (clips get trimmed) | — |
| `--montage` | Combine all clips into one highlights video | off |
| `--narration TEXT` | TTS narration text to overlay | — |
| `--narration-voice` | TTS voice shortcut or full name | `male-en` |
| `--narration-vol` | Narration volume (0.0-1.0) | 1.0 |
| `--music FILE` | Path to music file to mix | — |
| `--music-ai` | AI suggests background music (copyright-safe) | off |
| `--music-genre TEXT` | Genre for music search | — |
| `--music-vol` | Original audio volume when music mixed | 0.05 |
| `--music-level` | Background music volume | 1.0 |
| `--translate LANG` | Translate captions to another language | — |
| `--upload` | Upload to YouTube Shorts after rendering | off |
| `--upload-privacy` | YouTube visibility: `private`, `unlisted`, `public` | `private` |

---

## Features

### Custom Prompt (`--prompt`)

Guide the LLM to look for specific types of moments:

```bash
# Find only funny moments
python -m src.main --input podcast.mp4 --prompt "find the funniest jokes and reactions"

# Find educational moments
python -m src.main --input lecture.mp4 --prompt "find moments where a concept is explained clearly with good examples"

# Find drama/conflict
python -m src.main --input stream.mp4 --prompt "find moments where people argue or disagree"
```

### Interactive Selection (`-i`)

After the LLM suggests clips, see a list and choose which ones to render:

```bash
python -m src.main --input video.mp4 -i
```

Output:
```
============================================================
CLIP CANDIDATES (sorted by virality score)
============================================================
  [1] 🤣 He Completely Lost It
      category: funniest | score: 95 | duration: 78s
      hook: "WAIT FOR THE ENDING"
      reason: Perfect comedic timing with unexpected punchline

  [2] 🔥 The Hot Take That Broke Chat
      category: best_hook | score: 91 | duration: 65s
      hook: "CONTROVERSIAL OPINION"
      reason: Bold opening claim hooks instantly

============================================================
Enter clip numbers to render (e.g. '1,3,5' or 'all'):
> 1,3
```

### Best Moments Montage (`--montage`)

Combine all selected clips into one single highlights video with crossfade transitions:

```bash
# Create a highlights reel from the top 5 moments
python -m src.main --input stream_vod.mp4 --montage

# Combine with interactive selection
python -m src.main --input stream_vod.mp4 -i --montage
```

### AI Music Suggestion (`--music-ai`)

Let the AI pick background music that matches your clip's mood from your local `music/` folder:

```bash
python -m src.main --input video.mp4 --music-ai
```

**Setup:** Download royalty-free tracks and put them in the `music/` folder with descriptive names:
```
music/
├── upbeat-energetic-pop.mp3
├── dark-suspenseful-ambient.mp3
├── funny-comedic-ukulele.mp3
├── chill-lofi-beats.mp3
├── epic-cinematic-orchestra.mp3
└── happy-acoustic-guitar.mp3
```

### YouTube Shorts Upload (`--upload`)

Automatically upload rendered clips to YouTube Shorts. The LLM generates optimized titles, descriptions, hashtags, and SEO tags from the clip content.

```bash
# Upload clips as private (default — review before publishing)
python -m src.main --input video.mp4 --upload

# Upload as public
python -m src.main --input video.mp4 --upload --upload-privacy public

# Upload montage
python -m src.main --input video.mp4 --montage --upload
```

**What the LLM generates for each upload:**
- Catchy title with emoji and power words
- Multi-line description with hook, context, call-to-action
- 15-20 hashtags (#Shorts #YouTubeShorts #viral + niche tags)
- 15-20 SEO tags for discoverability

**YouTube upload setup (one-time, free):**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable **YouTube Data API v3**
3. Go to **Credentials** → **Create OAuth client ID** → **Desktop app**
4. Download `client_secret.json` to the project root
5. First `--upload` run opens browser for Google sign-in (token cached after that)

### Combining everything

```bash
python -m src.main \
  --input my_stream.mp4 \
  --num-clips 8 \
  --prompt "find the most emotional and funny moments" \
  -i \
  --montage \
  --emoji \
  --music-ai \
  --reframe blur \
  --upload
```

This will:
1. Transcribe the video
2. Ask the LLM to find 8 emotional/funny moments
3. Show you the list — pick your favorites
4. AI suggests background music — you pick a track
5. Render each with blurred background reframing, captions, hook text, emoji, and music
6. Stitch them into one highlights video with transitions
7. Generate optimized YouTube metadata and upload as a Short

---

## Story Mode — Create narrated videos from a script

Creates short videos entirely from a narration script. AI generates illustrations for each scene, applies TTS voiceover with per-scene mood/voice control, and stitches everything together.

```bash
python -m src.main story --script script.txt --voice warm --visuals openai
```

### Story flags

| Flag | Description | Default |
|------|-------------|---------|
| `--script TEXT` | Narration script (text or path to .txt file) | required |
| `--voice` | Default TTS voice shortcut or full name | `warm` |
| `--voice-rate` | Default speech rate (e.g. `-30` = 30% slower) | auto |
| `--output-dir DIR` | Output directory | `./output` |
| `--visuals` | Visual source: `download`, `openai`, `sd` | `download` |
| `--music FILE` | Path to background music | — |
| `--music-ai` | AI suggests background music | off |
| `--music-genre TEXT` | Genre for music search | — |
| `--music-level` | Background music volume (0.0-1.0) | 0.3 |
| `--no-music` | Disable automatic background music | off |
| `--upload` | Upload to YouTube Shorts after rendering | off |
| `--upload-privacy` | YouTube visibility: `private`, `unlisted`, `public` | `private` |

### Visual sources (`--visuals`)

| Option | Description | Cost |
|--------|-------------|------|
| `download` | Download stock images/videos from Pexels and YouTube (default) | Free |
| `openai` | AI-generated illustrations via OpenAI (gpt-image-1) | ~$0.04/image |
| `sd` | AI-generated illustrations via local Stable Diffusion | Free (local GPU) |

Results are cached — re-running the same script won't re-generate images or re-call the LLM.

### Script formats

**Format 1 — Plain text (AI splits into scenes automatically):**

```bash
python -m src.main story \
  --script "The samurai lived by a strict code of honor. Every morning they practiced their swordsmanship at dawn. But one day, everything changed when a stranger arrived at the dojo." \
  --voice warm --visuals openai
```

**Format 2 — Timeline with per-scene control:**

```bash
python -m src.main story --script script.txt --voice warm --visuals openai
```

Where `script.txt` contains:

```
# Lines starting with # are comments
0:00 | The warrior stood alone at the gate | samurai temple | image | dramatic
0:06 | His heart pounded as shadows crept closer | dark forest | image | tension | -35%
0:14 | Then suddenly, everything exploded | explosion fire | video | excited
0:20 | But in the end, peace returned to the land | sunset peaceful | image | calm
0:28 | And they lived happily ever after | happy ending | image | warm | -20%
```

**Timeline format:**
```
TIMESTAMP | NARRATION TEXT | SEARCH KEYWORD | VISUAL TYPE | MOOD | RATE
```

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| Timestamp | Yes | Scene start time | `0:00`, `1:30`, `90` |
| Narration text | Yes | What the TTS will say | `The warrior stood alone` |
| Search keyword | No | Visual search term (AI generates if omitted) | `samurai temple` |
| Visual type | No | `image` or `video` (default: `image`) | `video` |
| Mood | No | Mood preset name (see table below) | `dramatic` |
| Rate | No | Speech speed override | `-30%`, `+10%` |

Fields after search keyword can be in **any order**. Duration of each scene = gap between timestamps. The last scene auto-extends to fit the speech.

### Mood presets

Each mood sets both the voice character and speech speed. You can override the speed with a custom rate in the same line.

| Mood | Voice style | Speed | Best for |
|------|------------|-------|----------|
| `dramatic` | Deep, authoritative | -25% | Thriller, drama |
| `tension` | Serious, suspenseful | -20% | Mystery, suspense |
| `intense` | High energy, urgent | -10% | Action, breaking news |
| `dark` | Deep British | -30% | Horror, dark stories |
| `warm` | Approachable, casual | -25% | Human stories, relatable |
| `caring` | Expressive, emotional | -25% | Emotional, touching |
| `storyteller` | Confident, natural | -20% | General storytelling |
| `friendly` | Light, considerate | -15% | Everyday content |
| `cheerful` | Upbeat, positive | -10% | Happy, positive |
| `sad` | Soft, emotional | -30% | Sad scenes, loss |
| `calm` | Relaxed, peaceful | -30% | Peaceful, meditation |
| `excited` | Lively, energetic | +5% | Exciting moments |
| `angry` | Fierce, intense | +5% | Conflict, rage |
| `whisper` | Soft, intimate | -35% | Secrets, intimate |
| `slow` | Very slow pacing | -40% | Dramatic pauses |
| `fast` | Quick pacing | +10% | Urgency, excitement |
| `tiktok` | Punchy, viral | -5% | Short-form social |
| `viral` | Energetic | -5% | Trending content |
| `cute` | Cartoon-like | -10% | Fun, quirky |
| `news` | Professional | -10% | Facts, reporting |
| `documentary` | Authoritative | -15% | Documentaries |
| `narrator` | Epic, cinematic | -15% | Epic narration |

**Example — mixing moods in one script:**

```
0:00 | It was a peaceful morning in the village | quiet village sunrise | image | calm
0:06 | The children played by the river, laughing | children playing river | image | cheerful
0:13 | But dark clouds gathered on the horizon | storm clouds dramatic | image | tension
0:20 | A terrible roar shook the earth | earthquake destruction | video | intense
0:26 | Silence fell over the ruins | ruins dust silence | image | sad | -35%
0:34 | Yet from the ashes, a flower bloomed | flower growing ruins | image | warm
0:42 | And hope was reborn | sunrise new beginning | image | dramatic
```

### Story examples

```bash
# AI-generated illustrations with OpenAI, dramatic voice
python -m src.main story \
  --script script.txt \
  --voice warm \
  --visuals openai \
  --music-ai

# Local Stable Diffusion illustrations (free)
python -m src.main story \
  --script script.txt \
  --visuals sd \
  --voice storyteller

# Downloaded stock visuals (default, no API key needed)
python -m src.main story \
  --script "Artificial intelligence is changing the world." \
  --voice female-en

# Indonesian narration
python -m src.main story \
  --script "Pada zaman dahulu ada seorang raja." \
  --voice male-id

# Upload to YouTube Shorts after rendering
python -m src.main story \
  --script script.txt \
  --visuals openai \
  --voice warm \
  --upload --upload-privacy private
```

### How story mode works

1. **Parse script** — splits into scenes (by timeline or AI). Per-scene mood/voice settings are extracted.
2. **Generate TTS** — creates voiceover for each scene using Edge TTS with the scene's voice and speed.
3. **Generate/find visuals** — AI-generates illustrations (OpenAI/SD) or downloads stock images/videos.
4. **Reframe** — crops/resizes all visuals to 9:16 vertical with Ken Burns zoom effect.
5. **Subtitle** — burns narration text onto each scene.
6. **Stitch** — concatenates all scenes with crossfade transitions.
7. **Merge** — combines visual track with full narration audio.
8. **Music** — optionally adds AI-selected background music.
9. **Upload** — optionally uploads to YouTube Shorts with LLM-optimized metadata.

Output: `output/story_output.mp4`

### Available TTS voices

| Shortcut | Voice | Style |
|----------|-------|-------|
| `dramatic` | en-US-ChristopherNeural | Deep, authoritative |
| `tension` | en-US-EricNeural | Serious, rational |
| `intense` | en-US-RogerNeural | Lively, high energy |
| `dark` | en-GB-ThomasNeural | Deep British |
| `storyteller` | en-US-AndrewNeural | Warm, confident |
| `warm` | en-US-BrianNeural | Approachable, casual |
| `caring` | en-US-AvaNeural | Expressive, emotional |
| `friendly` | en-US-JennyNeural | Friendly, considerate |
| `cheerful` | en-US-EmmaNeural | Cheerful, clear |
| `news` | en-US-AriaNeural | Positive, confident |
| `narrator` | en-US-GuyNeural | Passionate, cinematic |
| `tiktok` | en-US-GuyNeural | Punchy, viral |
| `male-en` | en-US-ChristopherNeural | Standard male |
| `female-en` | en-US-JennyNeural | Standard female |
| `male-id` | id-ID-ArdiNeural | Indonesian male |
| `female-id` | id-ID-GadisNeural | Indonesian female |
| `male-uk` | en-GB-RyanNeural | British male |
| `female-uk` | en-GB-SoniaNeural | British female |
| `male-au` | en-AU-WilliamNeural | Australian male |
| `female-au` | en-AU-NatashaNeural | Australian female |

Run `edge-tts --list-voices` for all 400+ available voices.

---

## Output examples

### Individual clips (without `--montage`)

```
output/
├── clip_01_funniest_95.mp4
├── clip_02_best_hook_91.mp4
├── clip_03_insightful_88.mp4
├── clip_04_most_engaging_85.mp4
└── clip_05_suspenseful_82.mp4
```

### Montage mode (with `--montage`)

```
output/
└── montage_best_moments.mp4    # Single combined highlights video
```

### Story mode

```
output/
├── narration_full.mp3          # Full TTS narration audio
└── story_output.mp4            # Final narrated video
```

---

## Configuration (`.env`)

```env
# ── LLM (clip selection, metadata generation) ──────────────────────────
LLM_PROVIDER=groq                        # "groq" (free) or "anthropic" (paid)
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# Anthropic (only needed if LLM_PROVIDER=anthropic)
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# ── Transcription ──────────────────────────────────────────────────────
TRANSCRIPTION_PROVIDER=groq               # "groq" (cloud, fast) or "local" (faster-whisper)
GROQ_WHISPER_MODEL=whisper-large-v3-turbo

# Local whisper settings (only if TRANSCRIPTION_PROVIDER=local)
WHISPER_MODEL_SIZE=medium
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto

# ── Story mode visuals ─────────────────────────────────────────────────
# Pexels stock images/videos (free key at https://www.pexels.com/api/)
PEXELS_API_KEY=

# OpenAI image generation (needed if --visuals openai)
OPENAI_API_KEY=sk-...
OPENAI_IMAGE_MODEL=gpt-image-1           # or gpt-image-1-mini (cheaper)

# Stable Diffusion local API (needed if --visuals sd)
SD_API_URL=http://127.0.0.1:7860         # automatic1111 / Forge / ComfyUI

# ── YouTube Upload ─────────────────────────────────────────────────────
# OAuth client_secret.json path (default: ./client_secret.json)
# Get it from Google Cloud Console → YouTube Data API v3 → OAuth 2.0
YOUTUBE_CLIENT_SECRETS=client_secret.json

# ── Output ─────────────────────────────────────────────────────────────
OUTPUT_DIR=output
CLIP_MIN_SECONDS=60
CLIP_MAX_SECONDS=90
```

## Clip categories

The LLM assigns each clip to one of these categories:

| Category | What it looks for |
|----------|-------------------|
| `funniest` | Jokes, reactions, comedic timing |
| `suspenseful` | Tension, reveals, cliffhangers |
| `best_hook` | Strong opening that hooks instantly |
| `insightful` | Unique takes, clear explanations |
| `most_engaging` | High energy, audience interaction |

## Caching

Results are cached in `.cache/` to avoid duplicate API calls:
- **LLM responses** — clip selection, image prompts, metadata generation
- **Transcriptions** — audio transcription results
- **Generated images** — AI-generated illustrations (OpenAI/SD)

Delete `.cache/` to force re-generation.

## What's next (production path)

- **Smart reframing**: Face/saliency detection for dynamic crop tracking
- **Two-pass ranking**: Global comparison across all windows for better clip selection
- **Web UI**: Next.js dashboard with job queue (Redis/Celery)
- **Storage**: S3/R2 for source and rendered videos
- **Custom presets**: Save caption styles (font, color, animation)
