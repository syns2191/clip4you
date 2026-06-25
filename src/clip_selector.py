"""
Uses an LLM to read the timestamped transcript and pick the segments most
likely to work as standalone short-form clips.

Switch providers by setting LLM_PROVIDER=anthropic or LLM_PROVIDER=groq in .env.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from typing import List, Optional

from .config import settings
from .cache import cache_get, cache_set
from .transcribe import Segment, AudioEnergy, analyze_audio_energy

GROQ_TPM_LIMIT = 12_000
_groq_token_log: List[tuple] = []  # (timestamp, token_count)


def _groq_rate_wait(estimated_tokens: int) -> None:
    """Wait if needed to stay under Groq's 12k tokens-per-minute limit."""
    now = time.monotonic()
    # Expire entries older than 60s
    while _groq_token_log and now - _groq_token_log[0][0] > 60:
        _groq_token_log.pop(0)
    used = sum(t for _, t in _groq_token_log)
    if used + estimated_tokens > GROQ_TPM_LIMIT:
        oldest = _groq_token_log[0][0] if _groq_token_log else now
        wait = 60 - (now - oldest) + 1
        if wait > 0:
            print(f"   Groq rate limit: waiting {wait:.0f}s to stay under {GROQ_TPM_LIMIT} TPM...")
            time.sleep(wait)


def _groq_rate_record(tokens: int) -> None:
    _groq_token_log.append((time.monotonic(), tokens))

CHUNK_SECONDS = 20 * 60  # process the transcript in ~20 minute windows

BASE_RULES = """Each transcript line shows [start - end] in seconds. Use these exact \
timestamps for your clip boundaries — always start at the beginning of a \
sentence and end at the end of a sentence. Never cut mid-sentence.

AUDIO ENERGY ANNOTATIONS:
The transcript includes audio energy markers that show what's happening \
in the audio beyond just words. These are critical signals:
- 🔊 PEAK at Xs (+NdB) = Extreme volume spike — crowd roar, screaming, \
  commentator going wild, audience eruption. These are the MOST ENGAGING \
  moments. Build clips AROUND these peaks.
- 🔉 LOUD at Xs = Above-average energy — raised voices, excitement, \
  laughter, applause. Good supporting moments.
- 🔇 QUIET at Xs = Below-average energy — pauses, calm moments, silence. \
  These can be powerful as contrast BEFORE a peak (the calm before the storm).
- ⚡ ENERGY JUMP at Xs (+NdB) = Sudden volume explosion — something just \
  happened! The transition from quiet to loud is often the exact moment \
  worth clipping. Start 3-5 seconds BEFORE this jump.

USING AUDIO ENERGY FOR BETTER CLIPS:
- Prioritize clips that contain at least one 🔊 PEAK or ⚡ ENERGY JUMP
- The best clips ride an emotional wave: quiet buildup → energy jump → sustained peak → resolution
- When the transcript text seems boring but audio shows 🔊 PEAK, something \
  exciting is happening that words alone don't capture (crowd noise, music, reactions)
- A clip with 🔇 QUIET followed by 🔊 PEAK is usually better than one \
  that's 🔉 LOUD throughout — contrast creates impact
- Score clips with multiple audio peaks higher — they have more rewatchable moments

Core rules for ALL clips:
- Aim for clips between {min_s} and {max_s} seconds long. A few seconds over \
or under is OK if it means capturing a complete moment — never sacrifice a \
good start or ending just to hit the exact duration. But stay within \
{hard_min}–{hard_max} seconds as a hard boundary.
- Has a clear hook in the first 1-3 seconds that grabs attention immediately
- The clip must be self-contained — a viewer dropping in cold must understand it
- The ending must feel intentional — a punchline, a payoff, a reaction, a conclusion
- Never cut off before the payoff lands
- Include enough setup so the payoff has impact, and enough reaction so the audience feels satisfied

ENGAGEMENT BOOSTERS (apply these to maximize virality):
- Open-loop hooks: Start with a question, bold claim, or "wait for it" moment
- Pattern interrupt: Something unexpected happens that breaks the viewer's expectation
- Emotional peak: The clip should hit at least one strong emotion (shock, laughter, awe, anger, joy)
- Rewatchability: Clips people want to watch twice score higher
- Comment bait: Moments that make viewers want to argue, agree, or share their own experience
- Share trigger: "You HAVE to see this" moments that make viewers send it to friends
""".format(
    min_s=settings.clip_min_seconds,
    max_s=settings.clip_max_seconds,
    hard_min=max(15, settings.clip_min_seconds - 15),
    hard_max=settings.clip_max_seconds + 15,
)

VIDEO_CATEGORIES = {
    "sports": {
        "description": "Sports highlights, match footage, sports commentary",
        "prompt": """You are an elite sports highlights editor for viral social media content.

{base_rules}

SPORTS-SPECIFIC CUTTING RULES:
- GOALS/SCORES: Start 3-5 seconds BEFORE the key play begins (the buildup is crucial). Include the FULL celebration — never cut during celebration. The crowd reaction IS the payoff.
- SKILLS/TRICKS: Start just before the skill move. Include the defender being beaten and the crowd/commentator reaction.
- SAVES/BLOCKS: Include the dangerous attack that led to it. The "oh no" moment before the save makes the save feel incredible.
- FIGHTS/CONFRONTATIONS: Start at the trigger moment. Include teammates separating players, cards being shown.
- COMMENTATOR REACTIONS: When the commentator goes wild, that audio IS the hook. Start a few seconds before their peak excitement.
- CONTROVERSIAL MOMENTS: VAR checks, bad calls, offside debates — include the buildup AND the reaction.
- COMEBACKS: Show the deficit context briefly, then the turning point.
- Always prefer moments where audio energy peaks (commentator screaming, crowd roaring)
- End on the highest emotional note — the celebration, the replay, the stunned face
- CROWD ENERGY: The roar of the crowd is what makes sports clips feel ALIVE. Prioritize moments where the crowd is loudest — goals, last-minute winners, red cards, penalty decisions. These moments get enhanced with crowd roar sound effects automatically.
- CELEBRATION: Always extend the clip to include the FULL celebration — players running, sliding, hugging, crowd going wild. The celebration is often more viral than the goal itself.

Clip categories for sports: goal, skill_move, save, tackle, celebration, controversy, comeback, funny_moment, commentator_peak, crowd_reaction""",
    },
    "comedy": {
        "description": "Stand-up comedy, comedy sketches, funny podcasts",
        "prompt": """You are a comedy clip editor who has cut thousands of viral comedy shorts.

{base_rules}

COMEDY-SPECIFIC CUTTING RULES:
- SETUP + PUNCHLINE: ALWAYS include the FULL setup. A punchline without setup is worthless. Start at the beginning of the bit, not the middle.
- CALLBACK JOKES: If a joke references an earlier bit, include enough context so it still works standalone.
- CROWD WORK: Start when the comedian first addresses the audience member. Include the audience reaction — their laughter IS the payoff.
- PHYSICAL COMEDY: Include the buildup of anticipation. The funniest moment is often the REACTION to the physical comedy, not the act itself.
- TIMING IS EVERYTHING: Include the comedian's pauses and timing beats — don't trim them. The silence before a punchline is what makes it land.
- REACTION SHOTS: If the audience or other people react, include it. Other people laughing validates the humor for the viewer.
- END ON THE LAUGH: Cut right after the biggest laugh peak, or on the comedian's own laugh/break. Never cut during silence after a joke — that feels like the joke bombed.
- RULE OF THREE: If a comedian does a "three things" bit, include all three — the third is the punchline.
- CALLBACKS: If the punchline references something from the setup, make SURE the setup is in the clip.

Clip categories for comedy: punchline, crowd_work, physical_comedy, roast, storytelling, one_liner, callback, improv, awkward_moment, crowd_reaction""",
    },
    "reaction": {
        "description": "Reaction videos, first-time watches, try-not-to-laugh",
        "prompt": """You are a reaction video clip editor who maximizes emotional engagement.

{base_rules}

REACTION-SPECIFIC CUTTING RULES:
- THE ARC: A great reaction clip has three beats: (1) the reactor sees something, (2) they process it, (3) they react. Include ALL three.
- FIRST IMPRESSION: Start BEFORE the reactor sees the thing they react to. Their anticipation/setup makes the reaction more satisfying.
- GENUINE SURPRISE: Moments where the reactor is genuinely shocked, disgusted, scared, or delighted — these are gold. The more extreme and genuine, the better.
- FACIAL EXPRESSIONS: If you can tell from the transcript that the reactor is speechless or making sounds (gasps, screams, "oh my god"), that's a strong clip.
- CONTRAST: The best clips show a stark emotional shift — calm to chaos, confident to terrified, skeptical to blown away.
- COMMENTARY: Include the reactor's commentary AFTER their initial reaction — their analysis or jokes about what they just saw add value.
- DON'T CUT THE BUILDUP: If the reactor says "wait... wait... OH MY GOD" — include the full "wait wait" part. The anticipation makes the payoff better.
- GROUP REACTIONS: If multiple people react, include the chain reaction — one person's reaction triggering another's.
- End on the reactor's PEAK emotion or their funniest comment about what happened.

Clip categories for reaction: shock, disgust, amazement, fear, laughter, emotional, cringe, disbelief, wholesome, speechless""",
    },
    "podcast": {
        "description": "Podcasts, interviews, long-form conversations, talk shows",
        "prompt": """You are a podcast clip editor who turns long conversations into viral short-form clips.

{base_rules}

PODCAST-SPECIFIC CUTTING RULES:
- HOT TAKES: Bold, controversial, or surprising opinions are GOLD. Start right when the speaker begins their take — their confidence is the hook.
- STORIES: When someone tells a personal story, include the setup AND the payoff. The best clips have a mini narrative arc within them.
- DEBATES/DISAGREEMENTS: Start when tension first appears. Include both sides and the resolution or escalation. Conflict is engagement.
- VULNERABLE MOMENTS: When someone shares something personal, emotional, or raw — these go viral because they feel authentic.
- EXPERT DROPS: When a guest drops specialized knowledge that makes the listener go "I never thought of it that way" — that's clip-worthy.
- FUNNY TANGENTS: When the conversation goes off-rails in a funny way — include the derailment AND the laughter.
- QUOTABLE MOMENTS: One-liners, memorable phrases, "write that down" moments. These become the clip's hook text.
- Never start mid-thought. Find where the speaker begins their complete thought.
- End after the other person's reaction (agreement, pushback, laughter) — their response validates the moment.

Clip categories for podcast: hot_take, story, debate, vulnerable, mind_blown, funny, quotable, expert_insight, awkward, revelation""",
    },
    "gaming": {
        "description": "Gaming streams, Let's Plays, esports, gaming commentary",
        "prompt": """You are a gaming clip editor who cuts viral moments from streams and Let's Plays.

{base_rules}

GAMING-SPECIFIC CUTTING RULES:
- CLUTCH PLAYS: Include the full pressure situation — low health, last player alive, ticking clock. The context IS the content.
- RAGE/TILT: Start just before the triggering event. Include the buildup of frustration AND the explosion. The streamer's descent from calm to chaos is the arc.
- FAILS: Include the overconfidence or setup that precedes the fail. A fail without context is just "something went wrong." A fail after "watch this, chat" is comedy gold.
- VICTORIES/WINS: Include the final push AND the celebration. The streamer's genuine joy is the payoff.
- JUMP SCARES: Start a few seconds before so the viewer gets comfortable, then BAM. Include the full scream and recovery.
- CHAT INTERACTIONS: When the streamer reads chat and reacts — include the reading AND the reaction.
- SKILL MOMENTS: Insane aim, perfect timing, 200 IQ plays — include enough context so non-gamers can appreciate it.
- FUNNY BUGS/GLITCHES: The unexpected is gold. Include the "wait what" moment.
- End on the streamer's reaction — their emotion sells the clip.

Clip categories for gaming: clutch, rage, fail, victory, jumpscare, funny, skill_play, glitch, chat_moment, comeback""",
    },
    "music": {
        "description": "Music performances, concerts, music reviews, studio sessions",
        "prompt": """You are a music content clip editor who captures the most powerful musical moments.

{base_rules}

MUSIC-SPECIFIC CUTTING RULES:
- VOCAL PEAKS: The big note, the key change, the voice crack that gives chills — start 5-10 seconds before to build anticipation.
- CROWD SINGALONGS: When the crowd takes over and the artist steps back — that's magic. Include the transition from artist singing to crowd singing.
- INSTRUMENTAL SOLOS: The face-melting guitar solo, the drum breakdown — include the buildup and the crowd/band reaction after.
- EMOTIONAL MOMENTS: Artist getting emotional, crying, sharing a story about the song — raw authenticity goes viral.
- MASHUPS/COVERS: The moment the audience recognizes the song. That collective "OHHH" is the payoff.
- UNEXPECTED GENRE SWITCHES: When a performance shifts from one style to another — the surprise is the hook.
- AUDIENCE REACTIONS: When someone in the audience has an extreme reaction — tears, dancing, freaking out.
- End on an applause peak, a sustained note, or a powerful silence.

Clip categories for music: vocal_peak, crowd_moment, solo, emotional, cover, mashup, dance_break, audience_reaction, backstage, raw_talent""",
    },
    "educational": {
        "description": "Tutorials, lectures, explainers, how-to videos, TED talks",
        "prompt": """You are an educational content editor who makes learning feel exciting and shareable.

{base_rules}

EDUCATIONAL-SPECIFIC CUTTING RULES:
- AHA MOMENTS: When the speaker explains something that flips your understanding — the "mind blown" moment. Start from the misconception/question, end at the revelation.
- DEMONSTRATIONS: When the speaker shows rather than tells — include the full demonstration and the result.
- COUNTERINTUITIVE FACTS: "You've been doing this wrong your whole life" — these are viral hooks. Include the proof.
- STEP-BY-STEP: When a skill is shown, include enough steps that the viewer learns something actionable.
- ANALOGIES: Great explanations often use analogies. Include the analogy AND the concept it explains.
- BEFORE/AFTER: Showing the transformation — before the technique vs. after. Include both.
- MYTH BUSTING: "Everyone thinks X, but actually Y" — include the myth AND the truth.
- NUMBERS/STATS: When a shocking statistic is dropped, include the context that makes it shocking.
- End on the takeaway — the one thing the viewer should remember.

Clip categories for educational: mind_blown, demonstration, myth_bust, life_hack, explanation, before_after, statistic, analogy, technique, takeaway""",
    },
    "drama": {
        "description": "Reality TV, drama series, confrontations, arguments, roasts",
        "prompt": """You are a drama clip editor who captures maximum tension and conflict.

{base_rules}

DRAMA-SPECIFIC CUTTING RULES:
- CONFRONTATIONS: Start at the trigger — what caused the argument. Include the escalation AND the peak moment. Don't cut before the mic-drop line.
- REVEALS/TWISTS: Build to the reveal. Include enough "normal" before the twist so the contrast hits hard.
- EMOTIONAL BREAKDOWNS: Start when the emotion first cracks through. Include the full breakdown — cutting it short feels exploitative rather than engaging.
- SHADE/SUBTLE DIGS: The delivery matters. Include the pause, the look, the reaction of others in the room.
- ALLIANCES/BETRAYALS: Show the trust, then the betrayal. The "I trusted you" arc in 60 seconds.
- VOTING/ELIMINATION: Include the tension of not knowing, the announcement, and the immediate reaction.
- CONFESSIONALS/TO-CAMERA: When someone breaks the fourth wall with a killer one-liner about the drama.
- End on the most dramatic reaction — the gasp, the silence, the walk-off, the tears.

Clip categories for drama: confrontation, reveal, breakdown, shade, betrayal, elimination, confession, cliffhanger, reconciliation, villain_moment""",
    },
    "news": {
        "description": "News commentary, political discussion, current events, debates",
        "prompt": """You are a news clip editor who captures the most impactful and shareable moments from commentary and debate.

{base_rules}

NEWS-SPECIFIC CUTTING RULES:
- GOTCHA MOMENTS: When a host or guest catches someone in a contradiction — include the claim AND the counter-evidence.
- HEATED EXCHANGES: Start at the first sign of tension. Include the full exchange — interruptions, raised voices, the peak.
- BREAKING ANALYSIS: When someone explains WHY something matters, not just what happened. The "here's what nobody is talking about" angle.
- PREDICTIONS: Bold predictions that make viewers want to save and check later. Include the reasoning.
- EMOTIONAL APPEALS: When a speaker gets personal or passionate about an issue — authenticity cuts through.
- DATA DROPS: When a shocking statistic or fact changes the argument. Include the context.
- CROWD/AUDIENCE REACTIONS: Applause, boos, gasps — these validate the moment.
- End on the strongest statement or the most powerful silence.

Clip categories for news: gotcha, heated_exchange, analysis, prediction, emotional, data_bomb, audience_reaction, monologue, debate_win, breaking""",
    },
    "vlog": {
        "description": "Daily vlogs, travel content, lifestyle videos, day-in-the-life",
        "prompt": """You are a vlog editor who picks the most relatable and shareable personal moments.

{base_rules}

VLOG-SPECIFIC CUTTING RULES:
- UNEXPECTED MOMENTS: When plans go wrong, surprises happen, or reality doesn't match expectations — the unplanned moments are the best content.
- GENUINE EMOTIONS: Real joy, frustration, excitement, fear — not performed, but felt. The viewer connects to authenticity.
- BEAUTIFUL/STUNNING VISUALS: When the vlogger encounters something visually incredible — include their verbal reaction describing what they see.
- FOOD/TASTE REACTIONS: First bites, unexpected flavors — include the anticipation AND the honest reaction.
- INTERACTIONS WITH LOCALS: Genuine conversations, funny misunderstandings, kind strangers — these humanize the content.
- CHALLENGES/ATTEMPTS: When the vlogger tries something scary, difficult, or new. Include the fear, the attempt, and the result.
- End on the emotional peak — the view from the summit, the taste of the dish, the laughter with a stranger.

Clip categories for vlog: unexpected, emotional, stunning_view, food_reaction, local_encounter, challenge, funny, transformation, adventure, wholesome""",
    },
    "fitness": {
        "description": "Workout videos, fitness transformations, gym content, sports training",
        "prompt": """You are a fitness content editor who creates motivational and shareable clips.

{base_rules}

FITNESS-SPECIFIC CUTTING RULES:
- PR/PERSONAL RECORDS: Include the buildup (loading the bar, getting set), the lift, AND the celebration. The struggle is the story.
- TECHNIQUE BREAKDOWNS: When someone corrects form or explains a movement — include the wrong way AND the right way for maximum value.
- TRANSFORMATIONS: Before/after moments, progress updates — include specific numbers or visible changes.
- FAILS (SAFE ONES): Gym fails where nobody gets hurt — the overconfidence, the attempt, the failure. Comedy gold.
- MOTIVATIONAL MOMENTS: When a trainer pushes someone past their limit. Include the struggle AND the triumph.
- REACTIONS TO OTHERS: When someone spots an incredible lift or physique — genuine amazement.
- End on the achievement, the exhausted triumph, or the motivational one-liner.

Clip categories for fitness: pr_attempt, technique, transformation, fail, motivation, reaction, challenge, workout_tip, before_after, beast_mode""",
    },
    "cooking": {
        "description": "Cooking shows, recipe videos, food reviews, mukbang",
        "prompt": """You are a food content editor who captures the most satisfying and shareable moments.

{base_rules}

COOKING-SPECIFIC CUTTING RULES:
- MONEY SHOTS: The cheese pull, the sauce pour, the cross-section reveal — include the buildup of anticipation.
- TASTE REACTIONS: First bite reactions, unexpected flavors, spice challenges — include the full reaction arc.
- TECHNIQUE REVEALS: When a chef shows a skill or trick — include the "watch this" setup and the result.
- FAILURES: Kitchen disasters, burnt food, wrong ingredients — include the realization moment.
- DEBATES: Food opinions, "this is not real Italian" moments — controversial food takes go viral.
- TRANSFORMATIONS: Raw to cooked, ugly to beautiful plating — the before and after.
- End on the most satisfying visual (the perfect dish) or the strongest taste reaction.

Clip categories for cooking: money_shot, taste_reaction, technique, disaster, food_debate, transformation, hack, challenge, review, satisfying""",
    },
    "asmr": {
        "description": "ASMR, relaxation, satisfying videos, oddly satisfying content",
        "prompt": """You are an ASMR/satisfying content editor who captures the most tingle-inducing moments.

{base_rules}

ASMR/SATISFYING-SPECIFIC CUTTING RULES:
- PEAK TINGLES: Find the moments with the most intense or varied sounds/visuals.
- TRANSITIONS: When one satisfying action flows into another — the seamless transition between triggers.
- UNEXPECTED SOUNDS: When a new material or technique produces a surprising sound — include the moment of discovery.
- VISUAL SATISFACTION: Peeling, popping, organizing, cleaning — include the full completion of the action.
- WHISPER MOMENTS: When the speaker says something funny, surprising, or intimate in a whisper — the contrast is engaging.
- SEQUENCES: A series of increasingly satisfying actions that build toward a peak.
- End on the most satisfying completion — the last peel, the final tap, the perfect alignment.

Clip categories for asmr: tingles, visual_satisfaction, whisper, crunch, liquid, tapping, roleplay, unboxing, organization, nature""",
    },
    "auto": {
        "description": "Auto-detect video category from transcript content",
        "prompt": None,
    },
}

AUTO_DETECT_PROMPT = """Based on this transcript excerpt, what type of video is this? Pick ONE from: {categories}

Transcript excerpt:
{excerpt}

Return ONLY the category name, nothing else."""

CATEGORY_PROMPT_TEMPLATE = """{category_prompt}

Return ONLY valid JSON, no markdown fences, no commentary. Schema:
{{{{
  "clips": [
    {{{{
      "start": <float seconds>,
      "end": <float seconds>,
      "title": "<short punchy title, max 8 words>",
      "hook_text": "<on-screen top-text hook, max 6 words>",
      "category": "<clip sub-category from the list above>",
      "emoji": "<single emoji that fits the moment, e.g. 😂 🔥 😱 💯 😎 💀 🤯 ⚽ 🎵 🎮>",
      "score": <integer 1-100, your confidence this goes viral>,
      "reason": "<one sentence why this works>"
    }}}}
  ]
}}}}

If nothing in this window is clip-worthy, return {{{{"clips": []}}}}.
"""

GENERIC_PROMPT = """You are an expert short-form video editor who has cut \
thousands of viral TikTok/YouTube Shorts/Reels clips from long-form content. \
Given a timestamped transcript window, identify the segments that would make \
the strongest standalone clips.

{base_rules}

Clip categories: funniest, suspenseful, best_hook, insightful, most_engaging, \
emotional, controversial, wholesome, shocking, relatable"""


def _build_system_prompt(video_category: str = "auto") -> str:
    cat = VIDEO_CATEGORIES.get(video_category)
    if cat and cat.get("prompt"):
        prompt_body = cat["prompt"].format(base_rules=BASE_RULES)
    else:
        prompt_body = GENERIC_PROMPT.format(base_rules=BASE_RULES)
    return CATEGORY_PROMPT_TEMPLATE.format(category_prompt=prompt_body)


CATEGORY_EMOJI = {
    "funniest": "\U0001F602",
    "suspenseful": "\U0001F631",
    "best_hook": "\U0001F525",
    "insightful": "\U0001F4AF",
    "most_engaging": "\U0001F929",
    "emotional": "\U0001F622",
    "controversial": "\U0001F525",
    "wholesome": "\U00002764",
    "shocking": "\U0001F92F",
    "relatable": "\U0001F64F",
    # sports
    "goal": "\U000026BD",
    "skill_move": "\U0001F525",
    "save": "\U0001F9E4",
    "tackle": "\U0001F4AA",
    "celebration": "\U0001F389",
    "controversy": "\U0001F6A8",
    "comeback": "\U0001F525",
    "commentator_peak": "\U0001F399",
    "crowd_reaction": "\U0001F3DF",
    # comedy
    "punchline": "\U0001F602",
    "crowd_work": "\U0001F3A4",
    "physical_comedy": "\U0001F923",
    "roast": "\U0001F525",
    "storytelling": "\U0001F4D6",
    "one_liner": "\U0001F4A5",
    "callback": "\U0001F504",
    "improv": "\U0001F3AD",
    "awkward_moment": "\U0001F62C",
    # reaction
    "shock": "\U0001F631",
    "disgust": "\U0001F922",
    "amazement": "\U0001F929",
    "fear": "\U0001F628",
    "laughter": "\U0001F602",
    "cringe": "\U0001F648",
    "disbelief": "\U0001F92F",
    "speechless": "\U0001F636",
    # podcast
    "hot_take": "\U0001F525",
    "story": "\U0001F4D6",
    "debate": "\U00002694",
    "vulnerable": "\U0001F495",
    "mind_blown": "\U0001F92F",
    "funny": "\U0001F602",
    "quotable": "\U0001F4AC",
    "expert_insight": "\U0001F9E0",
    "awkward": "\U0001F62C",
    "revelation": "\U0001F4A1",
    # gaming
    "clutch": "\U0001F3AF",
    "rage": "\U0001F621",
    "fail": "\U0001F4A9",
    "victory": "\U0001F3C6",
    "jumpscare": "\U0001F631",
    "skill_play": "\U0001F3AE",
    "glitch": "\U0001F47E",
    "chat_moment": "\U0001F4AC",
    # drama
    "confrontation": "\U0001F4A2",
    "reveal": "\U0001F631",
    "breakdown": "\U0001F622",
    "shade": "\U0001F60F",
    "betrayal": "\U0001F5E1",
    "elimination": "\U0001F6AA",
    "confession": "\U0001F64A",
    "cliffhanger": "\U0001F62E",
    "reconciliation": "\U0001F91D",
    "villain_moment": "\U0001F608",
    # music
    "vocal_peak": "\U0001F3B5",
    "crowd_moment": "\U0001F3DF",
    "solo": "\U0001F3B8",
    "cover": "\U0001F3A4",
    "mashup": "\U0001F500",
    "dance_break": "\U0001F57A",
    "audience_reaction": "\U0001F44F",
    "backstage": "\U0001F3AC",
    "raw_talent": "\U0001F31F",
    # educational
    "demonstration": "\U0001F52C",
    "myth_bust": "\U0001F4A5",
    "life_hack": "\U0001F4A1",
    "explanation": "\U0001F4DA",
    "before_after": "\U0001F504",
    "statistic": "\U0001F4CA",
    "analogy": "\U0001F9E9",
    "technique": "\U0001F527",
    "takeaway": "\U0001F4CC",
    # fitness
    "pr_attempt": "\U0001F4AA",
    "transformation": "\U0001F504",
    "motivation": "\U0001F525",
    "beast_mode": "\U0001F981",
    "workout_tip": "\U0001F4A1",
    # cooking
    "money_shot": "\U0001F924",
    "taste_reaction": "\U0001F60B",
    "disaster": "\U0001F4A5",
    "food_debate": "\U0001F525",
    "hack": "\U0001F4A1",
    "challenge": "\U0001F525",
    "review": "\U00002B50",
    "satisfying": "\U0001F60C",
    # generic fallbacks
    "unexpected": "\U0001F62E",
    "stunning_view": "\U0001F30D",
    "food_reaction": "\U0001F60B",
    "local_encounter": "\U0001F91D",
    "adventure": "\U0001F30D",
}


@dataclass
class ClipCandidate:
    start: float
    end: float
    title: str
    hook_text: str
    category: str
    score: int
    reason: str
    emoji: str = ""

    def __post_init__(self):
        if not self.emoji:
            self.emoji = CATEGORY_EMOJI.get(self.category, "\U0001F525")


def _segments_to_text(segments: List[Segment], energy: Optional[List[AudioEnergy]] = None) -> str:
    """Build enriched transcript with audio energy annotations interleaved."""
    if not energy:
        return "\n".join(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}" for seg in segments)

    # Build a timeline merging transcript lines and energy markers
    lines: List[str] = []
    energy_idx = 0

    # Pre-compute energy jumps
    jumps = set()
    for i in range(1, len(energy)):
        if energy[i].rms_db - energy[i - 1].rms_db > 10:
            jumps.add(i)

    for seg in segments:
        # Insert any energy markers that fall before this segment
        while energy_idx < len(energy) and energy[energy_idx].time <= seg.start:
            e = energy[energy_idx]
            if e.energy_level == "peak":
                diff = e.rms_db - (-60.0)
                lines.append(f"  🔊 PEAK at {e.time:.1f}s ({e.rms_db:+.0f}dB)")
            elif e.energy_level == "loud":
                lines.append(f"  🔉 LOUD at {e.time:.1f}s ({e.rms_db:+.0f}dB)")
            elif e.energy_level == "quiet":
                lines.append(f"  🔇 QUIET at {e.time:.1f}s ({e.rms_db:+.0f}dB)")
            if energy_idx in jumps:
                jump_db = energy[energy_idx].rms_db - energy[energy_idx - 1].rms_db
                lines.append(f"  ⚡ ENERGY JUMP at {e.time:.1f}s (+{jump_db:.0f}dB sudden spike!)")
            energy_idx += 1

        lines.append(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")

    # Remaining energy markers after last segment
    while energy_idx < len(energy):
        e = energy[energy_idx]
        if e.energy_level in ("peak", "loud"):
            lines.append(f"  🔊 {'PEAK' if e.energy_level == 'peak' else 'LOUD'} at {e.time:.1f}s ({e.rms_db:+.0f}dB)")
        if energy_idx in jumps:
            jump_db = energy[energy_idx].rms_db - energy[energy_idx - 1].rms_db
            lines.append(f"  ⚡ ENERGY JUMP at {e.time:.1f}s (+{jump_db:.0f}dB)")
        energy_idx += 1

    return "\n".join(lines)


def _chunk_segments(segments: List[Segment]) -> List[List[Segment]]:
    if not segments:
        return []
    video_duration = segments[-1].end - segments[0].start
    # Don't split short videos — one LLM call is enough
    if video_duration <= CHUNK_SECONDS * 1.5:
        return [segments]
    chunks: List[List[Segment]] = []
    current: List[Segment] = []
    chunk_start = segments[0].start
    for seg in segments:
        if seg.start - chunk_start > CHUNK_SECONDS and current:
            chunks.append(current)
            current = []
            chunk_start = seg.start
        current.append(seg)
    if current:
        chunks.append(current)
    return chunks


def _estimate_tokens(text: str) -> int:
    return len(text) // 3


def _call_llm(transcript_text: str, system_prompt: str = "") -> str:
    cache_key = hashlib.sha256(
        f"{settings.llm_provider}:{system_prompt}:{transcript_text}".encode()
    ).hexdigest()[:16]
    cached = cache_get("llm", cache_key)
    if cached is not None:
        return cached

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": transcript_text}],
        )
        result = "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        estimated = _estimate_tokens(system_prompt + transcript_text) + 2000
        _groq_rate_wait(estimated)

        client = Groq(api_key=settings.groq_api_key)
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=settings.groq_model,
                    max_tokens=2000,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": transcript_text},
                    ],
                )
                break
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    wait = 30 * (attempt + 1)
                    print(f"   Groq rate limited, retrying in {wait}s (attempt {attempt + 1}/3)...")
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError("Groq rate limit: failed after 3 retries")

        actual_tokens = getattr(response, "usage", None)
        if actual_tokens:
            _groq_rate_record(actual_tokens.total_tokens)
        else:
            _groq_rate_record(estimated)
        result = response.choices[0].message.content.strip()

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. Use 'anthropic' or 'groq'.")

    cache_set("llm", cache_key, result)
    return result


def _auto_detect_category(segments: List[Segment]) -> str:
    excerpt = _segments_to_text(segments[:30])
    categories = [k for k in VIDEO_CATEGORIES if k != "auto"]
    prompt = AUTO_DETECT_PROMPT.format(
        categories=", ".join(categories),
        excerpt=excerpt[:2000],
    )
    raw = _call_llm(prompt, system_prompt="You classify video content into categories. Return ONLY the category name.")
    detected = raw.strip().lower().replace('"', '').replace("'", "")
    for cat in categories:
        if cat in detected:
            return cat
    return "auto"


def _snap_boundaries(
    candidate: ClipCandidate,
    segments: List[Segment],
) -> ClipCandidate:
    """Snap clip start/end to sentence (segment) boundaries so cuts land on
    natural speech pauses instead of mid-word."""
    if not segments:
        return candidate

    # Find the segment whose start is closest to candidate.start
    # Prefer snapping backward so the hook sentence is fully included
    best_start_seg = min(segments, key=lambda s: abs(s.start - candidate.start))
    # Find the segment whose end is closest to candidate.end
    # Prefer snapping forward so the punchline sentence is fully included
    best_end_seg = min(segments, key=lambda s: abs(s.end - candidate.end))

    snapped_start = best_start_seg.start
    snapped_end = best_end_seg.end

    # If snapping pushed start after end, fall back
    if snapped_start >= snapped_end:
        return candidate

    duration = snapped_end - snapped_start

    # If too short after snapping, expand by adding adjacent segments
    if duration < settings.clip_min_seconds:
        seg_starts = [s.start for s in segments]
        seg_ends = [s.end for s in segments]
        start_idx = seg_starts.index(snapped_start) if snapped_start in seg_starts else 0
        end_idx = seg_ends.index(snapped_end) if snapped_end in seg_ends else len(segments) - 1

        while (snapped_end - snapped_start) < settings.clip_min_seconds:
            expanded = False
            # Try extending end first (preserve the punchline/payoff)
            if end_idx + 1 < len(segments):
                end_idx += 1
                snapped_end = segments[end_idx].end
                expanded = True
            # Then try extending start (add more setup)
            if (snapped_end - snapped_start) < settings.clip_min_seconds and start_idx > 0:
                start_idx -= 1
                snapped_start = segments[start_idx].start
                expanded = True
            if not expanded:
                break

    # If too long, trim from the start (keep the ending/punchline)
    hard_max = settings.clip_max_seconds + 15
    if (snapped_end - snapped_start) > hard_max:
        seg_starts = [s.start for s in segments]
        for s_start in seg_starts:
            if s_start >= snapped_start and (snapped_end - s_start) <= hard_max:
                snapped_start = s_start
                break

    # Add a small breath before the first word so the clip doesn't start abruptly
    snapped_start = max(0, snapped_start - 0.3)

    candidate.start = snapped_start
    candidate.end = snapped_end
    return candidate


def select_clips(
    segments: List[Segment],
    num_clips: int = 5,
    user_prompt: str = "",
    video_category: str = "auto",
    video_path: Optional[str] = None,
) -> List[ClipCandidate]:
    all_candidates: List[ClipCandidate] = []

    if video_category == "auto":
        detected = _auto_detect_category(segments)
        if detected != "auto":
            video_category = detected
            print(f"   Auto-detected video category: {video_category}")
        else:
            print(f"   Could not detect category, using generic mode")

    # Analyze audio energy for smarter clip selection
    energy: Optional[List[AudioEnergy]] = None
    if video_path:
        print(f"   Analyzing audio energy...")
        energy = analyze_audio_energy(video_path)
        if energy:
            spikes = sum(1 for e in energy if e.is_spike)
            peaks = sum(1 for e in energy if e.energy_level == "peak")
            print(f"   Found {spikes} energy spikes, {peaks} peak moments")
        else:
            print(f"   No audio energy data (silent or very short)")

    system_prompt = _build_system_prompt(video_category)

    for chunk in _chunk_segments(segments):
        # Get energy data for this chunk's time range
        chunk_energy = None
        if energy and chunk:
            chunk_start = chunk[0].start
            chunk_end = chunk[-1].end
            chunk_energy = [e for e in energy if chunk_start <= e.time <= chunk_end]

        transcript_text = _segments_to_text(chunk, energy=chunk_energy)
        if not transcript_text.strip():
            continue

        if user_prompt:
            transcript_text = (
                f"ADDITIONAL INSTRUCTIONS FROM THE USER:\n{user_prompt}\n\n"
                f"TRANSCRIPT:\n{transcript_text}"
            )

        print(transcript_text)
        print(system_prompt)

        raw = _call_llm(transcript_text, system_prompt=system_prompt)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for c in parsed.get("clips", []):
            try:
                candidate = ClipCandidate(**c)
            except TypeError:
                continue

            candidate = _snap_boundaries(candidate, chunk)

            duration = candidate.end - candidate.start
            hard_min = max(15, settings.clip_min_seconds - 15)
            hard_max = settings.clip_max_seconds + 15
            if duration > hard_max:
                continue
            if duration < hard_min:
                continue
            all_candidates.append(candidate)

    all_candidates.sort(key=lambda c: c.score, reverse=True)
    return all_candidates[:num_clips]
