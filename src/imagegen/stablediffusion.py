"""Stable Diffusion image generation via local API (automatic1111/Forge)."""
import base64
import json
import os
import shutil
import urllib.request
from typing import Optional

SD_API_URL = os.getenv("SD_API_URL", "http://127.0.0.1:7860")
SD_MODEL = os.getenv("SD_MODEL", "")
SD_WIDTH = int(os.getenv("SD_WIDTH", "512"))
SD_HEIGHT = int(os.getenv("SD_HEIGHT", "768"))


def _ensure_sd_model() -> None:
    """Switch SD model if SD_MODEL env var is set and differs from current."""
    if not SD_MODEL:
        return
    try:
        with urllib.request.urlopen(f"{SD_API_URL}/sdapi/v1/options", timeout=10) as resp:
            current = json.loads(resp.read().decode()).get("sd_model_checkpoint", "")
        if SD_MODEL not in current:
            print(f"      Switching SD model to {SD_MODEL}...")
            data = json.dumps({"sd_model_checkpoint": SD_MODEL}).encode()
            req = urllib.request.Request(
                f"{SD_API_URL}/sdapi/v1/options",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=120)
    except Exception:
        pass


def generate_stable_diffusion(
    prompt: str,
    output_path: str,
    width: int = SD_WIDTH,
    height: int = SD_HEIGHT,
    negative_prompt: str = "",
    sd_override: Optional[dict] = None,
) -> bool:
    return generate_stable_diffusion_with_reference(
        prompt, output_path, width=width, height=height,
        negative_prompt=negative_prompt, sd_override=sd_override,
    )


def generate_stable_diffusion_with_reference(
    prompt: str,
    output_path: str,
    width: int = SD_WIDTH,
    height: int = SD_HEIGHT,
    negative_prompt: str = "",
    sd_override: Optional[dict] = None,
    reference_image_path: str = "",
) -> bool:
    """Generate an SD image, optionally with a reference image via IP-Adapter FaceID."""
    _ensure_sd_model()

    if not negative_prompt:
        negative_prompt = "text, watermark, logo, blurry, low quality, deformed, ugly, nsfw"

    payload = {
        "prompt": f"{prompt}<lora:ip-adapter-faceid-plusv2_sd15_lora:1>",
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": 8,
        "cfg_scale": 1.5,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "batch_size": 2,
    }
    if sd_override:
        payload.update(sd_override)

    if reference_image_path and os.path.exists(reference_image_path):
        with open(reference_image_path, "rb") as f:
            ref_b64 = base64.b64encode(f.read()).decode()
        payload["alwayson_scripts"] = {
            "IP-Adapter": {
                "args": [{
                    "enabled": True,
                    "image": ref_b64,
                    "model": "ip-adapter-faceid-plusv2_sd15",
                    "weight": 0.7,
                    "start": 0.0,
                    "end": 1.0,
                }]
            }
        }

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{SD_API_URL}/sdapi/v1/txt2img",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            images = json.loads(resp.read().decode()).get("images", [])

        if not images:
            return False

        base, ext = os.path.splitext(output_path)
        ext = ext or ".png"
        saved = []
        for i, img_b64 in enumerate(images):
            p = f"{base}_v{i+1}{ext}" if len(images) > 1 else output_path
            with open(p, "wb") as f:
                f.write(base64.b64decode(img_b64))
            if os.path.getsize(p) > 1000:
                saved.append(p)

        if not saved:
            return False
        shutil.copy2(saved[0], output_path)
        return True
    except Exception as e:
        print(f"      [Stable Diffusion error: {e}]")
        return False
