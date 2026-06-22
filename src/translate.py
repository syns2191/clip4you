"""
Translate caption text to another language using the LLM.
Preserves word-level timestamps by translating sentence groups
and redistributing timing across translated words.
"""
import json
from typing import List

from .config import settings
from .transcribe import Word


def translate_words(words: List[Word], target_language: str) -> List[Word]:
    """Translate a list of words to target language, preserving timing."""
    if not words:
        return words

    # Group words into sentences (by punctuation or chunks of ~15 words)
    chunks = _group_into_chunks(words)

    translated_words = []
    for chunk_words in chunks:
        original_text = " ".join(w.text for w in chunk_words)
        chunk_start = chunk_words[0].start
        chunk_end = chunk_words[-1].end
        chunk_duration = chunk_end - chunk_start

        translated_text = _translate_text(original_text, target_language)

        # Split translated text into words and distribute timing evenly
        trans_tokens = translated_text.split()
        if not trans_tokens:
            continue

        time_per_word = chunk_duration / len(trans_tokens)
        for j, token in enumerate(trans_tokens):
            w_start = chunk_start + j * time_per_word
            w_end = w_start + time_per_word
            translated_words.append(Word(text=token, start=w_start, end=w_end))

    return translated_words


def _group_into_chunks(words: List[Word], max_words: int = 15) -> List[List[Word]]:
    """Group words into sentence-like chunks for translation."""
    chunks = []
    current = []

    for w in words:
        current.append(w)
        # Split on sentence-ending punctuation or max words
        if (w.text.rstrip().endswith(('.', '!', '?', ','))
                and len(current) >= 3) or len(current) >= max_words:
            chunks.append(current)
            current = []

    if current:
        chunks.append(current)
    return chunks


def _translate_text(text: str, target_language: str) -> str:
    """Translate text using the LLM."""
    prompt = (
        f"Translate the following text to {target_language}. "
        f"Return ONLY the translated text, nothing else. "
        f"Keep it natural and concise.\n\n"
        f"Text: {text}"
    )

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    return text
