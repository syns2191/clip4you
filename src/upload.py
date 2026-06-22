"""Upload videos to YouTube Shorts via the YouTube Data API v3.
Uses LLM to generate engaging titles, descriptions, tags, and hashtags."""
import json
import os
import sys
from typing import Optional, List

from .config import settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

CLIENT_SECRETS_FILE = os.getenv(
    "YOUTUBE_CLIENT_SECRETS",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "client_secret.json"),
)
TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), ".youtube_token.json"
)

METADATA_PROMPT = """You are a YouTube Shorts optimization expert. Generate metadata that maximizes views, engagement, and discoverability.

Given this clip information, generate:
1. **Title**: Catchy, curiosity-driven, 50-70 chars. Use power words (shocking, insane, nobody knows, etc). Include 1 emoji at the start. Do NOT include #Shorts in the title.
2. **Description**: 3-5 sentences that:
   - First line: A hook that makes people want to watch (question or bold statement)
   - Second line: Brief context about what happens in the clip
   - Third line: Call to action (like, follow, comment)
   - Then 2 blank lines followed by a block of 15-20 hashtags (mix of broad + niche, always include #Shorts #YouTubeShorts #viral)
3. **Tags**: 15-20 SEO tags as a list. Mix broad terms (funny, viral, shorts) with specific niche terms related to the content.

CLIP INFO:
- Title: {title}
- Category: {category}
- Hook text: {hook_text}
- Why it's good: {reason}
- Emoji: {emoji}
- Virality score: {score}/100
{transcript_context}

Return ONLY valid JSON:
{{
  "title": "<optimized title with emoji, NO #Shorts>",
  "description": "<full description with hooks, context, CTA, and hashtag block>",
  "tags": ["tag1", "tag2", ...]
}}"""

STORY_METADATA_PROMPT = """You are a YouTube Shorts optimization expert. Generate metadata that maximizes views, engagement, and discoverability.

Given this story video script, generate:
1. **Title**: Catchy, emotional, curiosity-driven, 50-70 chars. Use power words. Include 1 emoji at the start. Do NOT include #Shorts in the title.
2. **Description**: 3-5 sentences that:
   - First line: A hook question or bold statement about the story
   - Second line: What the story is about without spoiling the ending
   - Third line: Call to action (like, follow, comment)
   - Then 2 blank lines followed by a block of 15-20 hashtags (include #Shorts #YouTubeShorts #viral #storytelling)
3. **Tags**: 15-20 SEO tags as a list.

SCRIPT:
{script}

Return ONLY valid JSON:
{{
  "title": "<optimized title with emoji, NO #Shorts>",
  "description": "<full description with hooks, context, CTA, and hashtag block>",
  "tags": ["tag1", "tag2", ...]
}}"""


def _generate_clip_metadata(
    title: str,
    category: str,
    hook_text: str,
    reason: str,
    emoji: str,
    score: int,
    transcript_snippet: str = "",
) -> dict:
    """Use LLM to generate optimized YouTube metadata for a clip."""
    transcript_context = ""
    if transcript_snippet:
        transcript_context = f"- Transcript snippet: \"{transcript_snippet}\""

    prompt = METADATA_PROMPT.format(
        title=title,
        category=category,
        hook_text=hook_text,
        reason=reason,
        emoji=emoji,
        score=score,
        transcript_context=transcript_context,
    )

    raw = _call_llm(prompt)

    try:
        data = json.loads(raw)
        return {
            "title": data.get("title", title),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
        }
    except (json.JSONDecodeError, KeyError):
        return {"title": title, "description": reason, "tags": [category]}


def _generate_story_metadata(script: str) -> dict:
    """Use LLM to generate optimized YouTube metadata for a story video."""
    script_preview = script[:1500]
    prompt = STORY_METADATA_PROMPT.format(script=script_preview)
    raw = _call_llm(prompt)

    try:
        data = json.loads(raw)
        return {
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
        }
    except (json.JSONDecodeError, KeyError):
        first_line = script.strip().split("\n")[0]
        if "|" in first_line:
            first_line = first_line.split("|")[1].strip()
        return {"title": first_line[:80], "description": "", "tags": []}


def _call_llm(prompt: str) -> str:
    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def _get_authenticated_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print(
                    f"\n[ERROR] YouTube client_secret.json not found at: {CLIENT_SECRETS_FILE}\n"
                    f"To set up YouTube upload:\n"
                    f"  1. Go to https://console.cloud.google.com/\n"
                    f"  2. Create a project and enable 'YouTube Data API v3'\n"
                    f"  3. Create OAuth 2.0 credentials (Desktop app)\n"
                    f"  4. Download client_secret.json to project root\n"
                    f"  5. Or set YOUTUBE_CLIENT_SECRETS env var to its path\n"
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build(API_SERVICE_NAME, API_VERSION, credentials=creds)


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str = "",
    tags: Optional[list] = None,
    privacy: str = "private",
    category_id: str = "22",
) -> str:
    """Upload a video to YouTube as a Short.

    Returns the YouTube video ID on success.
    """
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    if "#Shorts" not in title:
        title = f"{title} #Shorts"

    if tags is None:
        tags = []
    for required_tag in ["Shorts", "YouTubeShorts"]:
        if required_tag not in tags:
            tags.append(required_tag)

    if description and "#Shorts" not in description:
        description += "\n\n#Shorts"
    elif not description:
        description = "#Shorts"

    print(f"\n   Title: {title}")
    print(f"   Tags: {', '.join(tags[:10])}{'...' if len(tags) > 10 else ''}")
    print(f"   Privacy: {privacy}")
    desc_preview = description.split("\n")[0][:80]
    print(f"   Description: {desc_preview}...")

    youtube = _get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    print(f"   Uploading {os.path.basename(video_path)}...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"   {pct}% uploaded", end="\r")

    video_id = response["id"]
    print(f"   Upload complete: https://youtube.com/shorts/{video_id}")
    return video_id
