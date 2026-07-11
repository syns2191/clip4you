"""OpenAI image generation."""
import os
import urllib.request

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")


def generate_openai(prompt: str, output_path: str, size: str = "1024x1536") -> bool:
    """Generate an image using OpenAI (gpt-image-1, dall-e-3, etc)."""
    if not OPENAI_API_KEY:
        print("      [OPENAI_API_KEY not set, skipping]")
        return False

    try:
        import base64
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        print(f"      Using model: {OPENAI_IMAGE_MODEL}")

        response = client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size=size,
            quality="medium",
            n=1,
        )
        img = response.data[0]

        if hasattr(img, "b64_json") and img.b64_json:
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(img.b64_json))
        elif hasattr(img, "url") and img.url:
            urllib.request.urlretrieve(img.url, output_path)
        else:
            print("      [No image data in response]")
            return False

        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        print(f"      [OpenAI image error: {e}]")
        return False
