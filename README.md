# Clip4You

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
5. **`src/imagegen.py`** — AI image/video generation for story scenes (OpenAI, Stable Diffusion, or Google Veo).
6. **`src/enhance.py`** — AI-powered post-render enhancement (text overlays, zoom, speed, transitions).
7. **`src/scriptgen.py`** — AI script generator with character presets, background themes, and category guidance.
8. **`src/upload.py`** — automatic YouTube Shorts upload with LLM-optimized metadata.
9. **`src/main.py`** — orchestrates everything and writes finished `.mp4` files.

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
| `--category` | Video category for smarter cutting (see below) | `auto` |
| `--interactive` / `-i` | Pick which clips to render | off |
| `--clip-min SEC` | Min clip duration for selection | 60 (from .env) |
| `--clip-max SEC` | Max clip duration for selection | 90 (from .env) |
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
| `--sfx` | Add sound effect to all clips: `crowd`, `whoosh`, `impact`, `rise`, `drop`, `whistle`, `horn`, `buzzer` | — |
| `--sfx-vol` | Sound effect volume (0.0-1.0) | 0.6 |
| `--enhance` | AI-enhance clips after rendering (overlays, zoom, transitions) | off |
| `--enhance-prompt TEXT` | Custom instructions for enhancement | — |
| `--upload` | Upload to YouTube Shorts after rendering | off |
| `--upload-privacy` | YouTube visibility: `private`, `unlisted`, `public` | `private` |

---

## Features

### Video Category (`--category`)

Tell the AI what kind of video it's working with, and it uses genre-specific rules to find the perfect cut points. If you don't specify, it auto-detects from the transcript.

```bash
# Auto-detect (default) — AI figures out the genre from the transcript
python -m src.main --input video.mp4

# Sports — prioritizes goals, celebrations, skill moves, saves, crowd reactions
python -m src.main --input football_match.mp4 --category sports

# Comedy — finds complete setup+punchline, crowd work, callbacks
python -m src.main --input standup_special.mp4 --category comedy

# Reaction — captures full reaction arcs: sees content → processes → reacts
python -m src.main --input reaction_video.mp4 --category reaction

# Podcast — finds hot takes, debates, vulnerable moments, quotable one-liners
python -m src.main --input podcast_episode.mp4 --category podcast

# Gaming — clutch plays, rage moments, fails, jump scares, chat interactions
python -m src.main --input stream_vod.mp4 --category gaming

# Drama — confrontations, reveals, betrayals, emotional breakdowns
python -m src.main --input reality_show.mp4 --category drama

# Music — vocal peaks, crowd singalongs, solos, emotional artist moments
python -m src.main --input concert.mp4 --category music

# Educational — mind-blown moments, myth busting, demonstrations, life hacks
python -m src.main --input ted_talk.mp4 --category educational

# News — gotcha moments, heated exchanges, data bombs, monologues
python -m src.main --input news_debate.mp4 --category news

# Vlog — unexpected moments, food reactions, stunning views, local encounters
python -m src.main --input travel_vlog.mp4 --category vlog

# Fitness — PRs, technique breakdowns, transformations, motivational moments
python -m src.main --input gym_session.mp4 --category fitness

# Cooking — money shots, taste reactions, technique reveals, kitchen disasters
python -m src.main --input cooking_show.mp4 --category cooking

# ASMR — peak tingles, satisfying visuals, transitions, whisper moments
python -m src.main --input asmr_video.mp4 --category asmr
```

**Available categories:**

| Category | What the AI looks for | Best clip sub-types |
|----------|----------------------|---------------------|
| `sports` | Goals, saves, skills, crowd energy | goal, skill_move, save, celebration, commentator_peak |
| `comedy` | Complete jokes with setup + payoff | punchline, crowd_work, roast, callback, one_liner |
| `reaction` | Full reaction arcs (see → process → react) | shock, amazement, disbelief, cringe, emotional |
| `podcast` | Strong opinions, stories, debates | hot_take, debate, vulnerable, quotable, revelation |
| `gaming` | Peak moments from streams/gameplay | clutch, rage, fail, victory, jumpscare, skill_play |
| `drama` | Conflict, reveals, emotional peaks | confrontation, betrayal, breakdown, reveal, shade |
| `music` | Peak performances, crowd moments | vocal_peak, crowd_moment, solo, cover, emotional |
| `educational` | Aha moments, demonstrations, myths | mind_blown, myth_bust, life_hack, demonstration |
| `news` | Heated exchanges, gotcha moments | gotcha, heated_exchange, analysis, debate_win |
| `vlog` | Genuine moments, surprises, visuals | unexpected, food_reaction, stunning_view, adventure |
| `fitness` | PRs, form checks, transformations | pr_attempt, technique, transformation, beast_mode |
| `cooking` | Satisfying food moments, reactions | money_shot, taste_reaction, technique, disaster |
| `asmr` | Tingle-inducing triggers, satisfying content | tingles, visual_satisfaction, crunch, tapping |
| `auto` | Auto-detects from transcript (default) | varies |

**Combine with `--prompt` for even more specific results:**

```bash
# Sports + specific guidance
python -m src.main --input match.mp4 --category sports \
  --prompt "focus on Messi's plays and celebrations only"

# Comedy + specific guidance
python -m src.main --input standup.mp4 --category comedy \
  --prompt "only find jokes about relationships and dating"
```

### Audio Energy Analysis

The clip selector doesn't just read the transcript — it **analyzes the audio energy** of your video in a single ffmpeg pass. Volume spikes, crowd roars, commentator screams, laughter peaks, and sudden quiet-to-loud transitions are all detected and annotated in the transcript before the LLM sees it.

The LLM receives an enriched transcript like this:
```
  🔇 QUIET at 120.0s (-35dB)
[122.0s - 125.0s] and he takes the shot
  🔊 PEAK at 125.0s (-12dB)
  ⚡ ENERGY JUMP at 125.0s (+23dB sudden spike!)
[125.0s - 130.0s] GOAAAAL incredible finish
  🔉 LOUD at 128.0s (-14dB)
[130.0s - 140.0s] the crowd goes absolutely wild
```

This helps the AI find the best moments in **every category**:
- **Sports**: exact moment the crowd erupts for goals/saves
- **Comedy**: laughter peaks = where the joke landed
- **Reaction**: gasp/scream moment = peak reaction
- **Podcast**: raised voices = heated debates
- **Music**: vocal peak / crowd singalong moments
- **Gaming**: scream / rage / jumpscare audio spikes

Audio analysis runs automatically — no flags needed. Results are cached.

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

### Clip Preview & Interactive Selection

After the LLM finds clips, a rich preview is **always shown** with timestamps, scores, and a transcript preview of what's in each clip. With `-i`, you can pick which ones to render:

```bash
python -m src.main --input video.mp4 -i
```

Output:
```
======================================================================
  CLIP CANDIDATES (sorted by virality score)
======================================================================
  [1] ⚽ Enzo's Stunning Free Kick Goal
      ⏱  00:32.50 → 01:28.00  (56s)
      📊 category: goal | score: 95/100
      🪝 hook: "WHAT A STRIKE!"
      💡 Perfect free kick curled into top corner with insane crowd reaction
      💬 "he steps up, looks at the wall, and... GOAAAAL what a strike..."

  [2] 🔥 Messi's No-Look Pass
      ⏱  05:12.00 → 06:15.30  (63s)
      📊 category: skill_move | score: 88/100
      🪝 hook: "DID HE JUST DO THAT?"
      💡 Incredible no-look through ball splits the defense
      💬 "Messi receives it, doesn't even look, threads it through..."

======================================================================
Enter clip numbers to render (e.g. '1,3,5' or 'all'):
> 1,3
```

Without `-i`, the preview is shown but all clips render automatically.

### Clip Duration Override (`--clip-min`, `--clip-max`)

Override the default clip duration range per-run without editing `.env`:

```bash
# Short clips for TikTok (30-45 seconds)
python -m src.main --input video.mp4 --clip-min 30 --clip-max 45

# Longer clips for YouTube (90-120 seconds)
python -m src.main --input video.mp4 --clip-min 90 --clip-max 120
```

The LLM aims for clips within this range but has ±15 seconds tolerance to capture complete moments — it won't cut mid-sentence just to hit exact duration.

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

### Sound Effects (`--sfx`)

Add a synthesized sound effect to every rendered clip. No external audio files needed — all effects are generated on-the-fly by ffmpeg.

```bash
# Add crowd roar to sports clips (stadium atmosphere)
python -m src.main --input match.mp4 --category sports --sfx crowd

# Add whoosh transitions
python -m src.main --input video.mp4 --sfx whoosh

# Add impact hit sound
python -m src.main --input video.mp4 --sfx impact

# Control volume (0.0-1.0)
python -m src.main --input match.mp4 --sfx crowd --sfx-vol 0.8

# Combine with music and other features
python -m src.main --input match.mp4 --category sports --sfx crowd --music-ai --enhance
```

**Available effects:**

| Effect | Sound | Best for |
|--------|-------|----------|
| `crowd` | Stadium crowd roar (full clip duration) | Sports goals, celebrations, victories |
| `whoosh` | Fast swoosh/transition | Camera angle changes, scene transitions |
| `impact` | Low bass hit | Collisions, tackles, dramatic moments |
| `rise` | Building tension swell | Before a big reveal, buildup moments |
| `drop` | Bass drop | After a buildup, punchline landing |
| `whistle` | Referee/sports whistle | Sports starts, fouls, timeouts |
| `horn` | Stadium horn/vuvuzela | Goal celebrations, match starts |
| `buzzer` | Game buzzer | End of game/round, time's up moments |

> **Tip:** For sports clips, `--sfx crowd` adds the stadium atmosphere that makes highlights feel alive. For AI-controlled per-moment SFX placement (different effects at different timestamps), use `--enhance` instead — the AI decides what goes where.

### AI Clip Enhancement (`--enhance`)

After rendering, let the AI analyze each clip and automatically apply enhancements — text overlays, zoom effects, speed changes, and flash transitions — to make the clip more engaging and polished.

```bash
# Auto-enhance all clips after rendering
python -m src.main --input video.mp4 --enhance

# Enhance with custom instructions
python -m src.main --input video.mp4 --enhance \
  --enhance-prompt "add zoom on reaction moments, add text 'Wait for it...' before the punchline"

# Combine with other features
python -m src.main --input video.mp4 --enhance --music-ai --emoji --upload
```

**What the AI can do:**

| Enhancement | What it does | Example |
|-------------|-------------|---------|
| `text_overlay` | Add text at a specific timestamp | "A Star is Born" appears at 00:46 during celebration |
| `zoom` | Subtle zoom (1.2x-1.5x) for emphasis | Zoom into reaction face at punchline |
| `speed` | Speed up or slow down a section | Slow-mo the key moment, speed through boring setup |
| `flash` | White flash between scene changes | Quick flash to smooth a jarring cut at 00:15 |
| `crowd_roar` | Stadium crowd cheering SFX | Crowd roar layered over goal celebration at 00:32 |
| `sound_effect` | Short SFX: whoosh, impact, rise, drop | Whoosh on camera transition, bass drop on reveal |

The AI reads the clip's transcript, timestamps, and context to decide what actually helps — it won't add effects just for the sake of it.

**Example with custom prompt:**

```bash
python -m src.main --input football_highlights.mp4 --category sports --enhance \
  --enhance-prompt "Smooth the transitions between different camera angles. \
Add text overlays for goal scorers' names. \
Zoom in on celebration reactions. Add crowd roar on goals."
```

Output during rendering:
```
-> Rendering clip 1/3: Enzo's Stunning Goal (score 95)
   Enhancing clip...
   Analyzing clip for enhancements...
   Applying 5 enhancement(s)...
      [1/5] crowd_roar: Stadium atmosphere for goal celebration
      [2/5] text_overlay: Player name 'ENZO FERNANDEZ' during celebration
      [3/5] zoom: Emphasizes crowd reaction at punchline
      [4/5] sound_effect: Whoosh transition between camera angles
      [5/5] flash: Smooths camera angle transition at 00:15
   saved -> output/clip_01_goal_95.mp4
```

**Sports clips with crowd roar:**

The `crowd_roar` enhancement generates a synthesized stadium crowd cheering sound and layers it on top of the original audio at the right moment — goals, celebrations, amazing plays. No external sound files needed. The AI decides when and how loud based on the clip content.

```bash
# Full sports pipeline: smart cutting + crowd roar + text overlays
python -m src.main --input match.mp4 --category sports --enhance

# Just enhance an existing clip with crowd sound
python -m src.main enhance --input output/goal_clip.mp4 \
  --prompt "add crowd roar during the celebration, whoosh on camera transitions"
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

### Upload a File Directly (`upload` subcommand)

Upload an existing video file to YouTube Shorts without going through the full pipeline:

```bash
# AI generates title, description, and tags automatically
python -m src.main upload --input output/clip_01_funniest_95.mp4

# Provide your own title, let AI fill in the rest
python -m src.main upload --input output/clip_01.mp4 --title "My Cool Video"

# Fully manual — no AI metadata
python -m src.main upload --input output/clip_01.mp4 \
  --no-ai --title "My Title" --description "Check this out" --tags "funny,viral,shorts"

# Set privacy
python -m src.main upload --input output/clip_01.mp4 --privacy public
```

### Enhance an Existing Video (`enhance` subcommand)

Run AI enhancement on a video that's already been rendered — no need to re-run the full pipeline:

```bash
# Basic — AI decides what to enhance
python -m src.main enhance --input output/clip_01_funniest_95.mp4

# With custom instructions
python -m src.main enhance --input output/clip_01.mp4 \
  --prompt "add a zoom on the reaction at 00:08, add text 'No way!' at 00:12"

# Provide title for better AI context
python -m src.main enhance --input output/clip_01.mp4 \
  --title "Enzo's Stunning Goal" \
  --prompt "smooth transitions, add player name overlays"

# Custom output path
python -m src.main enhance --input output/clip_01.mp4 --output output/clip_01_v2.mp4
```

| Flag | Description | Default |
|------|-------------|---------|
| `--input FILE` | Path to the video file to enhance | required |
| `--output FILE` | Output path | `<input>_enhanced.mp4` |
| `--title TEXT` | Clip title (helps AI understand context) | — |
| `--prompt TEXT` | Custom enhancement instructions | — |

### Combining everything

```bash
python -m src.main \
  --input my_stream.mp4 \
  --category gaming \
  --num-clips 8 \
  --prompt "find the most emotional and funny moments" \
  -i \
  --montage \
  --emoji \
  --music-ai \
  --enhance \
  --enhance-prompt "zoom on reactions, add text overlays for key moments" \
  --reframe blur \
  --upload
```

This will:
1. Transcribe the video
2. Detect it's a gaming stream (or use `--category gaming`) and load gaming-specific clip rules
3. Ask the LLM to find 8 emotional/funny moments using gaming-aware criteria (clutch plays, rage, fails, etc.)
4. Show you the list — pick your favorites
5. AI suggests background music — you pick a track
6. Render each with blurred background reframing, captions, hook text, emoji, and music
7. AI enhances each clip — adds zoom, text overlays, transitions based on content
8. Stitch them into one highlights video with transitions
9. Show you the rendered videos — pick which ones to upload
10. Generate optimized YouTube metadata and upload as a Short

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
| `--visuals` | Visual source: `download`, `openai`, `sd`, `veo` | `download` |
| `--art-style` | Art style for AI images/video (see below) | auto |
| `--image-category` | Image category — auto-selects style + mood (see below) | — |
| `--animation` | Image animation: `zoom-in`, `zoom-out`, `pan-left`, `pan-right`, `pan-up`, `pan-down`, `zoom-pan`, `ken-burns`, `static` | `ken-burns` |
| `--film-grain` | Film effect: `light`, `medium`, `heavy`, `vintage` | — |
| `--caption-style` | Caption style: `default` (karaoke) or `bubble` (thought bubbles) | `default` |
| `--caption-font` | Caption font style (see font table below) | auto |
| `--caption-animation` | Caption animation: `karaoke`, `word`, or `typing` (see below) | `karaoke` |
| `--hook-text` | Hook text overlay on intro: `auto` (AI-generated) or custom text | — |
| `--review-images` | Review generated images and regenerate before rendering | off |
| `--music FILE` | Path to background music | — |
| `--music-ai` | AI suggests background music | off |
| `--music-genre TEXT` | Genre for music search | — |
| `--music-level` | Background music volume (0.0-1.0) | 0.3 |
| `--no-music` | Disable automatic background music | off |
| `--upload` | Upload to YouTube Shorts after rendering | off |
| `--upload-privacy` | YouTube visibility: `private`, `unlisted`, `public` | `private` |

### Visual sources (`--visuals`)

| Option | Output | Description | Cost |
|--------|--------|-------------|------|
| `download` | Images/videos | Stock photos/videos from Pexels and YouTube (default) | Free |
| `openai` | Images | AI-generated illustrations via OpenAI (gpt-image-1) | ~$0.04/image |
| `sd` | Images | AI-generated illustrations via local Stable Diffusion | Free (local GPU) |
| `veo` | **Video** | AI-generated video with voice + SFX via Google Veo | API pricing |

Results are cached — re-running the same script won't re-generate images/videos or re-call the LLM.

### Art Styles (`--art-style`)

Control the visual style of AI-generated images and videos:

```bash
# Pen & ink drawing style
python -m src.main story --script script.txt --visuals sd --art-style pen

# Stick figure animation
python -m src.main story --script script.txt --visuals veo --art-style stickfigure

# Watercolor painting
python -m src.main story --script script.txt --visuals openai --art-style watercolor

# Anime style
python -m src.main story --script script.txt --visuals sd --art-style anime
```

**Available styles:**

| Style | Look |
|-------|------|
| `pen` | Black ink pen drawing on white paper, crosshatching |
| `pencil` | Graphite pencil sketch, realistic shading |
| `watercolor` | Soft washes, flowing colors, paper texture |
| `anime` | Studio Ghibli style anime illustration |
| `cinematic` | Epic digital concept art (default) |
| `oil` | Classical oil painting, canvas texture |
| `comic` | Bold outlines, cel shading, graphic novel |
| `minimal` | Clean lines, flat design, negative space |
| `pixel` | 16-bit retro pixel art |
| `charcoal` | Dramatic charcoal drawing, high contrast |
| `storybook` | Whimsical children's book illustration |
| `realistic` | Photorealistic, sharp focus |
| `stickfigure` | Simple stick figure doodle, whiteboard sketch |
| `sketch` | Pencil sketch with LoRA, black & white graphite |
| `ghibli` | Studio Ghibli / Hayao Miyazaki style, hand-drawn, vivid colors |

### Image Categories (`--image-category`)

Auto-selects the best art style and mood for your content type:

```bash
# Meditation — auto-selects watercolor style with serene mood
python -m src.main story --script script.txt --visuals sd --image-category meditation

# Horror — auto-selects charcoal style with dark mood
python -m src.main story --script script.txt --visuals sd --image-category horror

# Fantasy — auto-selects cinematic style with magical mood
python -m src.main story --script script.txt --visuals openai --image-category fantasy
```

| Category | Auto style | Mood |
|----------|-----------|------|
| `meditation` | watercolor | serene, peaceful, calm |
| `zen` | pen | minimal, peaceful, balanced |
| `horror` | charcoal | dark, ominous, terrifying |
| `fantasy` | cinematic | magical, ethereal, epic |
| `romance` | watercolor | warm, intimate, tender |
| `motivational` | cinematic | powerful, inspiring |
| `history` | oil | ancient, grand, dramatic |
| `scifi` | cinematic | futuristic, neon, cosmic |
| `nature` | watercolor | natural, organic, peaceful |
| `adventure` | cinematic | epic, vast, dramatic |
| `comedy` | comic | funny, playful, bright |
| `mystery` | charcoal | mysterious, dark, foggy |
| `documentary` | realistic | authentic, journalistic |
| `fairytale` | storybook | whimsical, enchanted |
| `gaming` | pixel | retro, nostalgic, vibrant |
| `anime` | anime | dynamic, expressive |

You can combine `--art-style` and `--image-category` — the explicit style overrides the category's default.

### Google Veo AI Video (`--visuals veo`)

Generate actual **animated video clips** with natural voice narration and sound effects using Google Veo. Unlike other visual sources that generate static images, Veo creates real video with motion, voice, and ambient audio.

```bash
# Veo generates video with its own voice + SFX per scene
python -m src.main story --script script.txt --visuals veo

# Stick figure animation with Veo
python -m src.main story --script script.txt --visuals veo --art-style stickfigure

# Veo + background music on top
python -m src.main story --script script.txt --visuals veo --music-ai

# Veo with meditation category
python -m src.main story --script script.txt --visuals veo --image-category meditation
```

**How Veo differs from other visual sources:**
- **Generates video** (not static images) — real motion and animation
- **Includes voice** — Veo speaks the narration text naturally (skips edge-tts)
- **Includes sound effects** — ambient sounds, environment audio
- **No subtitles burned** — Veo already speaks the narration
- **Background music** is added on top via `--music` or `--music-ai`
- Each scene generates a 5-8 second clip, then all scenes are stitched together

**Setup:**
```bash
# Add to .env
GEMINI_API_KEY=your_key_here
```

Get your API key at [Google AI Studio](https://ai.studio/). Veo requires prepaid credits.

### Image Animation (`--animation`)

Control how static images move when converted to video:

```bash
# Ken Burns (default) — varies per scene automatically
python -m src.main story --script script.txt --visuals sd --animation ken-burns

# Slow zoom in
python -m src.main story --script script.txt --visuals sd --animation zoom-in

# No movement
python -m src.main story --script script.txt --visuals sd --animation static
```

| Preset | Effect |
|--------|--------|
| `zoom-in` | Slow zoom into center |
| `zoom-out` | Start zoomed, pull back |
| `pan-left` | Slow pan right to left |
| `pan-right` | Slow pan left to right |
| `pan-up` | Slow pan bottom to top |
| `pan-down` | Slow pan top to bottom |
| `zoom-pan` | Zoom in while panning right |
| `ken-burns` | Cycles through effects per scene (default) |
| `static` | No movement |

### Film Grain & Vintage (`--film-grain`)

Add film grain, noise, or a full vintage film look:

```bash
# Subtle grain
python -m src.main story --script script.txt --visuals sd --film-grain light

# Documentary feel
python -m src.main story --script script.txt --visuals sd --film-grain medium

# Full vintage film — sepia, heavy grain, scratches, vignette, flicker
python -m src.main story --script script.txt --visuals sd --film-grain vintage

# 35mm film texture — organic grain, warm halation, filmic contrast
python -m src.main story --script script.txt --visuals sd --film-grain 35mm

# Gritty cinematic — crushed blacks, teal-orange grade, harsh contrast
python -m src.main story --script script.txt --visuals sd --film-grain gritty

# Noise overlay — dense visible grain, minimal color shift
python -m src.main story --script script.txt --visuals sd --film-grain noise-overlay

# Retro — warm amber tint, faded blacks, film scratches, projector flicker
python -m src.main story --script script.txt --visuals sd --film-grain retro
```

| Effect | Description |
|--------|-------------|
| `light` | Subtle grain, 90% saturation |
| `medium` | Visible grain, 85% saturation, vignette |
| `heavy` | Strong grain, 75% saturation, heavy vignette |
| `vintage` | Full old film look: heavy grain, sepia tone, film scratches, projector flicker, strong vignette |
| `35mm` | 35mm film texture: fine organic grain, warm highlight shift, halation bloom, filmic contrast |
| `gritty` | Gritty cinematic: crushed blacks, heavy grain, desaturated, teal-orange grade, harsh contrast |
| `noise-overlay` | Dense visible noise overlay across all channels, slight desaturation, no color shift |
| `retro` | Retro look: warm amber tint, faded blacks, heavy grain, film scratches, projector flicker |

### Caption Styles (`--caption-style`)

Choose between cinematic karaoke captions or comic-style thought bubbles:

```bash
# Default — karaoke captions (full chunk, active word highlighted)
python -m src.main story --script script.txt --visuals sd --caption-style default

# Thought bubbles — doodle cloud near character's head
python -m src.main story --script script.txt --visuals sd --caption-style bubble
```

**Default captions:** Uppercase, glow outline + shadow, word-by-word highlight synced to speech.

**Bubble captions:** Animated thought bubble with smooth cloud shape (8-bump cosine wave, dark stroke outline), 3 trail dots that pop in sequentially with easeOutBack spring animation, cloud that grows in with overshoot, and a gentle sine-bob idle float. Each bubble is rendered as a transparent animated video overlay at 25fps. Face detection positions the bubble near the character's head.

### Caption Animation (`--caption-animation`)

Control how caption text appears on screen. Works with both `default` and `bubble` caption styles.

```bash
# Karaoke — full chunk visible, highlights active word (default)
python -m src.main story --script script.txt --caption-animation karaoke

# Word — words appear one by one as spoken
python -m src.main story --script script.txt --caption-animation word

# Typing — character by character like human typing
python -m src.main story --script script.txt --caption-animation typing

# Combine with bubble style
python -m src.main story --script script.txt --caption-style bubble --caption-animation typing
```

| Animation | Effect | Best for |
|-----------|--------|----------|
| `karaoke` | Full chunk visible, active word highlighted and scaled | Classic subtitle feel, easy to read |
| `word` | Words appear one by one, building up the phrase | Clean reveal, good pacing |
| `typing` | Characters appear one by one like human writing | Engaging, personal, storytelling |

### Caption Fonts (`--caption-font`)

Choose from 11 fonts optimized for short-form video captions. Works with both caption styles.

```bash
# Impact font for meme-style bold captions
python -m src.main story --script script.txt --caption-font impact

# Chalkduster for playful handwritten look
python -m src.main story --script script.txt --caption-style bubble --caption-font chalkduster

# DIN for clean modern editorial feel
python -m src.main story --script script.txt --caption-font din

# Croissant One for elegant decorative captions
python -m src.main story --script script.txt --caption-font croissant
```

| Font | Style | Best for |
|------|-------|----------|
| `futura` | Clean modern sans-serif | Default captions (default) |
| `impact` | Heavy condensed | Meme-style, bold statements |
| `arial-black` | Thick sans-serif | High visibility |
| `georgia` | Elegant serif | Storytelling, narrative (bubble default) |
| `trebuchet` | Rounded sans-serif | Friendly, approachable |
| `verdana` | Wide sans-serif | Maximum screen readability |
| `din` | Geometric bold | Modern, editorial |
| `chalkduster` | Handwritten chalk | Casual, playful |
| `comic-sans` | Comic book style | Fun, informal |
| `times` | Classic serif | Formal, documentary |
| `croissant-one` | Decorative serif (Google Fonts) | Elegant, stylish, eye-catching |

### Hook Text Overlay (`--hook-text`)

Add a short hook/summary text overlay at the start of the video to grab viewers' attention. The text appears as a pill/badge that slides down from the top and fades out after a few seconds.

```bash
# AI generates a hook from the script (max 6 words)
python -m src.main story --script script.txt --hook-text auto

# Use your own custom hook text
python -m src.main story --script script.txt --hook-text "THE TRUTH NOBODY TELLS YOU"

# Combine with other features
python -m src.main story --script script.txt --visuals sd --art-style sketch \
  --hook-text auto --caption-style bubble --film-grain vintage
```

The hook overlay appears during the intro scene (up to 5 seconds), slides down from above, holds, then fades out. It sits at the top of the screen so it doesn't conflict with captions in the lower third.

### Image Review & Regeneration (`--review-images`)

Review all generated images before rendering and regenerate any that don't look right:

```bash
python -m src.main story --script script.txt --visuals sd --art-style sketch --review-images
```

After images generate, a preview folder opens in Finder:
```
============================================================
  SCENE IMAGE REVIEW
============================================================
  [1] [OK    ] "[INTRO] — silence —"
  [2] [OK    ] "The mountain stands tall against the morning..."
  [3] [OK    ] "And in its shadow, a river flows in silence."
============================================================
Commands:
  2,4     — regenerate scenes 2 and 4
  open 3  — open scene 3 image in Preview
  open    — open review folder
  done    — continue to render
>
```

Regenerate as many times as you want until all images look right. Cache is cleared for regenerated scenes so SD produces a fresh image with a new seed.

### Silent Scenes

Mark scenes as silent (no voice) using brackets or dashes:

```
0:00 | [INTRO] — silence — | black screen | image | cinematic
0:05 | [PAUSE] | transition scene | image
0:10 | [music only] | landscape | image
0:15 | ... | fade scene | image
```

These generate silent audio — no TTS, no captions burned.

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

Each mood changes the **intonation** (pitch + speed) of the voice — the voice actor stays the same as whatever you set with `--voice`. This means "dramatic" makes the same voice deeper and slower, not a different person.

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
# Ghibli style with vintage film grain + thought bubble captions
python -m src.main story \
  --script script.txt \
  --visuals sd \
  --art-style ghibli \
  --film-grain vintage \
  --caption-style bubble \
  --caption-font chalkduster \
  --animation ken-burns \
  --music-ai

# Sketch style with image review before rendering
python -m src.main story \
  --script script.txt \
  --visuals sd \
  --art-style sketch \
  --review-images \
  --caption-style bubble \
  --caption-font georgia

# Stick figure meditation video with Veo (AI video + voice + SFX)
python -m src.main story \
  --script script.txt \
  --visuals veo \
  --art-style stickfigure \
  --image-category meditation \
  --music-ai

# Pen drawing style with Stable Diffusion (free, local)
python -m src.main story \
  --script script.txt \
  --visuals sd \
  --art-style pen \
  --voice warm

# Watercolor fantasy illustrations with OpenAI
python -m src.main story \
  --script script.txt \
  --visuals openai \
  --image-category fantasy \
  --music-ai

# Downloaded stock visuals (default, no API key needed)
python -m src.main story \
  --script "Artificial intelligence is changing the world." \
  --voice female-en

# Upload to YouTube Shorts after rendering
python -m src.main story \
  --script script.txt \
  --visuals openai \
  --voice warm \
  --upload --upload-privacy private
```

### How story mode works

**Standard flow** (download/openai/sd):
1. **Parse script** — splits into scenes (by timeline or AI). Per-scene mood settings extracted.
2. **Generate TTS** — creates voiceover per scene. Mood changes intonation (pitch + rate), not the voice actor.
3. **Generate visuals** — AI-generates images or downloads stock visuals. Detects faces for bubble caption positioning.
4. **Review** (if `--review-images`) — preview images, regenerate any that don't look right.
5. **Animate** — converts images to video with selected animation (Ken Burns, zoom, pan, etc.).
6. **Stitch** — concatenates all scenes with crossfade transitions.
7. **Merge** — combines visual track with full narration audio.
8. **Music** — optionally adds AI-selected background music.
9. **Transcribe** — transcribes the final video to get word-level timestamps for captions.
10. **Captions** — burns word-synced captions (karaoke style or animated thought bubbles with sequential reveal).
11. **Film grain** (if `--film-grain`) — applies grain/vintage noise effect.
12. **Upload** — optionally uploads to YouTube Shorts with LLM-optimized metadata.

**Veo flow** (`--visuals veo`):
1. **Parse script** — same as above.
2. **Skip TTS** — Veo generates its own natural voice narration.
3. **Generate video** — Veo creates 5-8s animated video clips per scene with voice + SFX.
4. **Stitch** — concatenates all Veo clips keeping their audio.
5. **Music** — optionally layers background music on top of Veo's audio.
6. **Upload** — same as above.

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

## Script Generator — AI-powered script creation

Generate complete story scripts with AI, ready to render. The LLM creates narration text, detailed visual descriptions for each scene, mood settings, and timing — all in the timeline format.

```bash
python -m src.main scriptgen --topic "why most people never change" --category stoic
```

### Scriptgen flags

| Flag | Description | Default |
|------|-------------|---------|
| `--topic TEXT` | What the story is about | required |
| `--category` | Script genre (see below) | `life-lesson` |
| `--art-style` | Art style for visual descriptions | `sketch` |
| `--character` | Character preset for consistent appearance | — |
| `--background` | Background theme for consistent environment | — |
| `--duration SEC` | Target video duration in seconds | 60 |
| `--tone TEXT` | Narration tone | `reflective and powerful` |
| `--output FILE` | Save script to file (default: print to stdout) | — |
| `--prompt TEXT` | Extra instructions for the AI | — |
| `--run` | Generate script AND immediately render as video | off |

### Script categories

| Category | What the AI writes |
|----------|-------------------|
| `stoic` | Stoic philosophy — Marcus Aurelius, Epictetus, discipline, resilience |
| `motivation` | Overcoming adversity, taking action, breaking comfort zones |
| `meditation` | Stillness, presence, letting go, breath, acceptance |
| `horror` | Slow dread, suggestion over gore, isolation, the unknown |
| `love` | Romance, self-love, loss, longing — honest and vulnerable |
| `psychology` | Human mind, cognitive biases, behavior patterns |
| `history` | Historical events and figures brought to life |
| `philosophy` | Big questions about existence, meaning, morality |
| `nature` | Natural world, cycles of life, wilderness, seasons |
| `scifi` | Near-future scenarios, technology's impact on humanity |
| `mystery` | Unsolved puzzles, strange phenomena, curiosity |
| `life-lesson` | Universal truths, practical wisdom (default) |
| `dark` | Shadow side of human nature, uncomfortable truths |
| `faith` | Spiritual themes, faith, doubt, grace |
| `money` | Financial wisdom, wealth mindset |
| `relationship` | Communication, boundaries, attachment, growth |

### Character presets (`--character`)

Define the main character's appearance — stays consistent across all scenes:

| Preset | Description |
|--------|-------------|
| `man` | Adult male, medium build |
| `woman` | Adult female, graceful posture |
| `elder` | Gray hair, weathered face, wise expression, robes |
| `youth` | Youthful face, casual clothing, curious |
| `warrior` | Battle-worn armor, scarred, determined |
| `monk` | Shaved head, simple robes, serene expression |
| `child` | Small figure, innocent expression |
| `silhouette` | Dark outline, featureless, mysterious |
| `stickman` | Simple line drawing, basic human shape |
| `businessman` | Suit, tie, briefcase |
| `artist` | Paint-stained clothes, messy hair |
| `samurai` | Traditional armor, katana, topknot hair |
| `philosopher` | Toga, sandals, long beard, scroll |
| `traveler` | Worn cloak, backpack, walking staff |
| `robot` | Sleek metal body, glowing eyes, futuristic |
| `girl` | Long hair, simple dress, gentle expression |

### Background themes (`--background`)

Define the environment — stays consistent across all scenes:

| Theme | Setting |
|-------|---------|
| `nature` | Rolling hills, trees, grass, vast sky |
| `urban` | City streets, buildings, modern architecture |
| `forest` | Dense trees, filtered canopy light, moss |
| `ocean` | Waves, coastline, sandy beach, horizon |
| `mountain` | Peaks, rocky terrain, valleys, snow |
| `temple` | Stone ruins, ancient columns, sacred architecture |
| `desert` | Sand dunes, empty horizon, heat haze |
| `space` | Starfield, nebula, cosmic void |
| `minimal` | Clean empty background, negative space |
| `rain` | Rain falling, wet surfaces, overcast |
| `night` | Dark sky, stars, moonlight |
| `countryside` | Rolling fields, farmland, wildflowers |
| `underwater` | Deep ocean, coral, light rays from surface |
| `ruins` | Crumbling walls, overgrown vegetation |
| `library` | Towering bookshelves, dusty books, candlelight |
| `battlefield` | Scarred terrain, broken weapons, smoke |
| `greek` | Marble columns, Greek agora, olive trees, amphitheater |

### Scriptgen examples

```bash
# Stoic philosophy with monk in mountains
python -m src.main scriptgen \
  --topic "the price of discipline" \
  --category stoic \
  --character monk \
  --background mountain \
  --art-style sketch

# Ancient Greek philosophy
python -m src.main scriptgen \
  --topic "what Socrates knew about death" \
  --category philosophy \
  --character philosopher \
  --background greek

# Dark psychological story
python -m src.main scriptgen \
  --topic "the mask you wear every day" \
  --category dark \
  --character silhouette \
  --background rain \
  --tone "haunting and intimate"

# Meditation guide
python -m src.main scriptgen \
  --topic "finding stillness in chaos" \
  --category meditation \
  --character monk \
  --background temple \
  --tone "calm and gentle"

# Generate + render immediately
python -m src.main scriptgen \
  --topic "why comfort is the enemy" \
  --category motivation \
  --character traveler \
  --background mountain \
  --art-style sketch \
  --duration 120 \
  --run

# Save to file, then render separately
python -m src.main scriptgen \
  --topic "the warrior's code" \
  --character samurai \
  --background temple \
  --output script.txt

python -m src.main story --script script.txt --visuals sd --art-style sketch
```

### How scriptgen works

1. You provide a topic, category, character, and background
2. The LLM generates a complete timeline script with:
   - Narration text per scene (what the voice says)
   - Detailed SD visual prompts (consistent character + background + art style)
   - Mood and speech rate per scene
   - Sequential timestamps
3. Output is in the exact timeline format story mode expects
4. Use `--run` to render immediately, or `--output` to save and edit before rendering

### Viral optimization

The script generator uses proven engagement patterns:

**Hook (first 3 seconds):** Uses one of 7 hook patterns — contrarian ("Everyone says X... they're wrong"), mystery, challenge, story loop, shock stat, direct attack, or promise. Creates an open loop that makes viewers stay.

**Retention (middle):** Injects micro-hooks every 8-10 seconds ("But here's the thing..."). Uses the 1-2 punch (setup expectation → subvert it). Short punchy sentences (max 15 words). Escalating emotional intensity.

**Ending (last scene):** Uses one of 5 ending patterns — callback to opening, cliff question, emotional peak, identity shift, or action call. Last line is quotable. Speech rate slows for impact.

**Visual storytelling:** Character's pose matches narration (struggle → kneeling, hope → standing tall). Environment evolves with emotional arc. Key symbol evolves through the story.

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
SD_MODEL=                                # e.g. realisticVisionV60B1_v51HyperVAE.safetensors
SD_WIDTH=512                             # Image width (default: 512)
SD_HEIGHT=768                            # Image height (default: 768)

# Google Veo AI video generation (needed if --visuals veo)
GEMINI_API_KEY=                           # Get at https://ai.studio/
VEO_MODEL=veo-3.1-lite-generate-preview  # or other Veo model

# ── YouTube Upload ─────────────────────────────────────────────────────
# OAuth client_secret.json path (default: ./client_secret.json)
# Get it from Google Cloud Console → YouTube Data API v3 → OAuth 2.0
YOUTUBE_CLIENT_SECRETS=client_secret.json

# ── Output ─────────────────────────────────────────────────────────────
OUTPUT_DIR=output
VIDEO_WIDTH=1080                         # Video output width (default: 1080)
VIDEO_HEIGHT=1920                        # Video output height (default: 1920)
CLIP_MIN_SECONDS=60
CLIP_MAX_SECONDS=90
```

## Clip sub-categories

Each clip gets assigned a sub-category based on the video type. When using `--category sports`, clips get labeled as `goal`, `celebration`, `skill_move`, etc. When using `--category comedy`, they get `punchline`, `crowd_work`, `roast`, etc. In generic/auto mode, the LLM uses these default categories:

| Category | What it looks for |
|----------|-------------------|
| `funniest` | Jokes, reactions, comedic timing |
| `suspenseful` | Tension, reveals, cliffhangers |
| `best_hook` | Strong opening that hooks instantly |
| `insightful` | Unique takes, clear explanations |
| `most_engaging` | High energy, audience interaction |
| `emotional` | Raw, authentic emotional moments |
| `controversial` | Bold opinions, hot takes |
| `wholesome` | Heartwarming, feel-good moments |
| `shocking` | Unexpected twists, surprises |
| `relatable` | "This is so me" moments |

## Caching

Results are cached in `.cache/` to avoid duplicate API calls:
- **LLM responses** — clip selection, image prompts, metadata generation
- **Transcriptions** — audio transcription results
- **Audio energy analysis** — volume/spike detection per video
- **Generated images** — AI-generated illustrations (OpenAI/SD)
- **Generated videos** — Veo-generated video clips

Delete `.cache/` to force re-generation.

## What's next (production path)

- **Smart reframing**: Face/saliency detection for dynamic crop tracking
- **Two-pass ranking**: Global comparison across all windows for better clip selection
- **Web UI**: Next.js dashboard with job queue (Redis/Celery)
- **Storage**: S3/R2 for source and rendered videos
- **Custom presets**: Save caption styles (font, color, animation)
