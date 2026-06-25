"""
Quick pipeline tests — run individual components without a real script.

Usage:
    # Run all tests
    python -m tests.test_pipeline

    # Run specific test
    python -m tests.test_pipeline image
    python -m tests.test_pipeline audio
    python -m tests.test_pipeline silent
    python -m tests.test_pipeline story
    python -m tests.test_pipeline styles
"""
import os
import sys
import shutil
import tempfile

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

TEST_OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_output")


def _setup():
    os.makedirs(TEST_OUTPUT, exist_ok=True)
    print(f"Test output: {TEST_OUTPUT}\n")


def _check_file(path: str, min_size: int = 1000) -> bool:
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    ok = exists and size > min_size
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {os.path.basename(path)} ({size:,} bytes)")
    return ok


# ── Image Generation Tests ───────────────────────────────────────────────

def test_image_sd_sketch():
    """Test SD image generation with sketch style."""
    from src.imagegen import generate_scene_image
    print("=== SD Image: sketch style ===")
    path = os.path.join(TEST_OUTPUT, "test_sketch.png")
    generate_scene_image(
        "A lonely man sits on a park bench at night",
        "man sitting park bench night",
        path,
        provider="sd",
        art_style="sketch",
    )
    return _check_file(path)


def test_image_sd_stickfigure():
    """Test SD image generation with stickfigure style."""
    from src.imagegen import generate_scene_image
    print("=== SD Image: stickfigure style ===")
    path = os.path.join(TEST_OUTPUT, "test_stickfigure.png")
    generate_scene_image(
        "Two friends high-fiving after winning a race",
        "friends high five celebration",
        path,
        provider="sd",
        art_style="stickfigure",
    )
    return _check_file(path)


def test_image_sd_watercolor():
    """Test SD image generation with watercolor style."""
    from src.imagegen import generate_scene_image
    print("=== SD Image: watercolor style ===")
    path = os.path.join(TEST_OUTPUT, "test_watercolor.png")
    generate_scene_image(
        "A peaceful garden with cherry blossoms falling",
        "cherry blossom garden peaceful",
        path,
        provider="sd",
        art_style="watercolor",
    )
    return _check_file(path)


def test_image_sd_category():
    """Test SD image generation with category auto-style."""
    from src.imagegen import generate_scene_image
    print("=== SD Image: meditation category (auto watercolor) ===")
    path = os.path.join(TEST_OUTPUT, "test_meditation.png")
    generate_scene_image(
        "Finding inner calm through deep breathing",
        "meditation breathing calm",
        path,
        provider="sd",
        category="meditation",
    )
    return _check_file(path)


def test_image_not_black():
    """Verify generated images have actual content (not all black)."""
    from src.imagegen import generate_stable_diffusion
    print("=== SD Image: black pixel check ===")
    path = os.path.join(TEST_OUTPUT, "test_black_check.png")
    generate_stable_diffusion("a cat sitting on a windowsill, sunny day", path)
    if not os.path.exists(path):
        print("  [FAIL] No file generated")
        return False
    from PIL import Image
    import numpy as np
    img = Image.open(path)
    avg = np.array(img).mean()
    ok = avg > 5
    print(f"  [{'PASS' if ok else 'FAIL'}] avg pixel: {avg:.0f} ({'has content' if ok else 'BLACK'})")
    return ok


# ── Audio / TTS Tests ────────────────────────────────────────────────────

def test_audio_basic():
    """Test basic TTS generation."""
    from src.narration import generate_narration
    print("=== Audio: basic TTS ===")
    path = os.path.join(TEST_OUTPUT, "test_tts_basic.mp3")
    generate_narration("The warrior stood alone at the gate.", path)
    return _check_file(path)


def test_audio_mood_dramatic():
    """Test TTS with dramatic mood (deep voice + low pitch)."""
    from src.narration import generate_narration
    print("=== Audio: dramatic mood ===")
    path = os.path.join(TEST_OUTPUT, "test_tts_dramatic.mp3")
    generate_narration("The darkness consumed everything in its path.", path, mood="dramatic")
    return _check_file(path)


def test_audio_mood_cheerful():
    """Test TTS with cheerful mood (bright voice + high pitch)."""
    from src.narration import generate_narration
    print("=== Audio: cheerful mood ===")
    path = os.path.join(TEST_OUTPUT, "test_tts_cheerful.mp3")
    generate_narration("What a beautiful day to be alive!", path, mood="cheerful")
    return _check_file(path)


def test_audio_mood_whisper():
    """Test TTS with whisper mood."""
    from src.narration import generate_narration
    print("=== Audio: whisper mood ===")
    path = os.path.join(TEST_OUTPUT, "test_tts_whisper.mp3")
    generate_narration("Can you hear it? The silence is deafening.", path, mood="whisper")
    return _check_file(path)


def test_audio_silent_scene():
    """Test silent scene detection and silence generation."""
    from src.narration import is_silent_scene, generate_silence
    print("=== Audio: silent scene detection ===")

    cases = [
        ("[INTRO] — silence —", True),
        ("[SILENCE]", True),
        ("[PAUSE]", True),
        ("[music only]", True),
        ("...", True),
        ("[END] — fade out —", True),
        ("The warrior stood alone", False),
        ("[INTRO] He looked up", False),
        ("", True),
    ]
    all_pass = True
    for text, expected in cases:
        result = is_silent_scene(text)
        ok = result == expected
        if not ok:
            all_pass = False
        print(f"  [{'PASS' if ok else 'FAIL'}] \"{text}\" → silent={result} (expected {expected})")

    path = os.path.join(TEST_OUTPUT, "test_silence.mp3")
    generate_silence(path, 3.0)
    file_ok = _check_file(path, min_size=100)
    return all_pass and file_ok


def test_audio_all_moods():
    """Generate audio for every mood to verify none crash."""
    from src.narration import generate_narration, MOOD_VOICE_SETTINGS
    print("=== Audio: all moods ===")
    all_pass = True
    for mood in MOOD_VOICE_SETTINGS:
        path = os.path.join(TEST_OUTPUT, f"test_mood_{mood}.mp3")
        try:
            generate_narration(f"Testing the {mood} mood.", path, mood=mood)
            ok = os.path.exists(path) and os.path.getsize(path) > 500
            print(f"  [{'PASS' if ok else 'FAIL'}] {mood}")
            if not ok:
                all_pass = False
        except Exception as e:
            print(f"  [FAIL] {mood}: {e}")
            all_pass = False
    return all_pass


# ── Style Tests ──────────────────────────────────────────────────────────

def test_all_styles():
    """Generate one image per art style to verify none produce black."""
    from src.imagegen import generate_scene_image, ART_STYLES
    print("=== SD Image: all styles ===")
    all_pass = True
    for style_key in ART_STYLES:
        path = os.path.join(TEST_OUTPUT, f"test_style_{style_key}.png")
        try:
            generate_scene_image(
                "A mountain landscape at sunset",
                "mountain sunset landscape",
                path,
                provider="sd",
                art_style=style_key,
            )
            if os.path.exists(path) and os.path.getsize(path) > 1000:
                from PIL import Image
                import numpy as np
                avg = np.array(Image.open(path)).mean()
                ok = avg > 5
                print(f"  [{'PASS' if ok else 'FAIL'}] {style_key:15s} ({os.path.getsize(path):>8,} bytes, avg={avg:.0f})")
                if not ok:
                    all_pass = False
            else:
                print(f"  [FAIL] {style_key:15s} (no file or too small)")
                all_pass = False
        except Exception as e:
            print(f"  [FAIL] {style_key:15s}: {e}")
            all_pass = False
    return all_pass


# ── Story Pipeline Test ──────────────────────────────────────────────────

def test_story_mini():
    """Test the full story pipeline with a 3-scene mini script."""
    from src.story import create_story
    print("=== Story: mini 3-scene pipeline ===")

    script = """0:00 | [INTRO] — silence — | black screen | image | cinematic
0:03 | The mountain stands tall against the morning sky. | mountain sunrise dramatic | image | dramatic
0:10 | And in its shadow, a river flows in silence. | river flowing mountain shadow | image | calm"""

    try:
        result = create_story(
            script=script,
            output_dir=os.path.join(TEST_OUTPUT, "story_mini"),
            voice="warm",
            visuals="sd",
            art_style="sketch",
            auto_music=False,
        )
        return _check_file(result, min_size=10000)
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def test_story_download():
    """Test story pipeline with download visuals (no API needed)."""
    from src.story import create_story
    print("=== Story: download visuals ===")

    script = """0:00 | The ocean stretches endlessly before us. | ocean waves horizon | image | calm
0:08 | A gentle breeze carries the scent of salt and freedom. | ocean breeze sunset | image | warm"""

    try:
        result = create_story(
            script=script,
            output_dir=os.path.join(TEST_OUTPUT, "story_download"),
            voice="warm",
            visuals="download",
            auto_music=False,
        )
        return _check_file(result, min_size=10000)
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


# ── Test Runner ──────────────────────────────────────────────────────────

TESTS = {
    "image": [
        test_image_sd_sketch,
        test_image_sd_stickfigure,
        test_image_sd_watercolor,
        test_image_sd_category,
        test_image_not_black,
    ],
    "audio": [
        test_audio_basic,
        test_audio_mood_dramatic,
        test_audio_mood_cheerful,
        test_audio_mood_whisper,
    ],
    "silent": [
        test_audio_silent_scene,
    ],
    "moods": [
        test_audio_all_moods,
    ],
    "styles": [
        test_all_styles,
    ],
    "story": [
        test_story_mini,
    ],
    "story-download": [
        test_story_download,
    ],
}


def main():
    _setup()

    # Pick which tests to run
    if len(sys.argv) > 1:
        groups = sys.argv[1:]
    else:
        groups = ["image", "audio", "silent"]

    passed = 0
    failed = 0

    for group in groups:
        if group == "all":
            test_list = [t for tests in TESTS.values() for t in tests]
        elif group in TESTS:
            test_list = TESTS[group]
        else:
            print(f"Unknown test group: {group}")
            print(f"Available: {', '.join(TESTS.keys())}, all")
            sys.exit(1)

        for test_fn in test_list:
            try:
                result = test_fn()
                if result:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"  [FAIL] Exception: {e}")
                failed += 1
            print()

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        print("Some tests FAILED")
        sys.exit(1)
    else:
        print("All tests PASSED")


if __name__ == "__main__":
    main()
