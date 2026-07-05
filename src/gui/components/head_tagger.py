"""Head position tagging controls for Gradio."""

import io
import base64
import os

import gradio as gr
from PIL import Image, ImageDraw

from ...render import detect_head_position
from ...config import settings


def render_head_preview_html(img_path, head_pos=None):
    """Render scene image as HTML with click-to-tag JS and optional crosshair."""
    if not img_path or not os.path.exists(img_path):
        return "<p style='color:#888'>No image available</p>"

    img = Image.open(img_path).convert("RGB")

    if head_pos:
        draw = ImageDraw.Draw(img)
        sx = img.width / 1080
        sy = img.height / 1920
        cx, cy = int(head_pos[0] * sx), int(head_pos[1] * sy)
        r = 15
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="red", width=3)
        draw.line([cx - r * 2, cy, cx + r * 2, cy], fill="red", width=2)
        draw.line([cx, cy - r * 2, cx, cy + r * 2], fill="red", width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    onclick_js = (
        "var rect=this.getBoundingClientRect();"
        "var x=Math.round((event.clientX-rect.left)/rect.width*1080);"
        "var y=Math.round((event.clientY-rect.top)/rect.height*1920);"
        "x=Math.max(0,Math.min(1080,x));y=Math.max(0,Math.min(1920,y));"
        "var ti=document.querySelector('#head_click_xy textarea, #head_click_xy input');"
        "if(ti){"
        "var setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value')"
        "||Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value');"
        "setter.set.call(ti,x+','+y+','+Date.now());"
        "ti.dispatchEvent(new Event('input',{bubbles:true}));"
        "}"
    )

    return (
        f'<img src="data:image/png;base64,{b64}" '
        f'style="max-height:400px;cursor:crosshair;display:block;border:1px solid #444;border-radius:4px;" '
        f'onclick="{onclick_js}" />'
    )


def on_click_set_head(session, idx, xy_raw):
    """Handle click-to-tag from JS. `xy_raw` is 'x,y,timestamp'.
    Returns (head_x, head_y, head_status, preview_html, session)."""
    if session is None or idx is None or not xy_raw:
        return 0, 0, "No session", "", session
    try:
        x_str, y_str, _ts = str(xy_raw).split(",")
        x, y = int(x_str), int(y_str)
    except (ValueError, TypeError):
        return 0, 0, "No session", "", session
    x = max(0, min(x, 1080))
    y = max(0, min(y, 1920))
    session.scenes[idx].head_pos = (x, y)
    img_path = session.scene_img_paths[idx]
    preview = render_head_preview_html(img_path, (x, y))
    return x, y, f"Set to ({x}, {y})", preview, session


def create_head_controls():
    """Create head position UI controls. Returns (container, components dict)."""
    with gr.Group() as container:
        gr.Markdown("**Head Position** (for thought bubble placement)")
        with gr.Row():
            head_x = gr.Number(label="X", value=0, precision=0)
            head_y = gr.Number(label="Y", value=0, precision=0)
        with gr.Row():
            auto_btn = gr.Button("Auto Detect", size="sm")
            set_btn = gr.Button("Set Manual", size="sm", variant="primary")
            clear_btn = gr.Button("Clear", size="sm")
        head_status = gr.Textbox(label="Status", interactive=False, lines=1)

    return container, {
        "head_x": head_x,
        "head_y": head_y,
        "auto_btn": auto_btn,
        "set_btn": set_btn,
        "clear_btn": clear_btn,
        "head_status": head_status,
    }


def auto_detect_head(session_state, scene_idx):
    print("Auto-detecting head position...")
    """Run auto head detection. Returns (x, y, status, preview_html)."""
    if session_state is None or scene_idx is None:
        return 0, 0, "No session", ""
    img_path = session_state.scene_img_paths[scene_idx]
    if not img_path:
        return 0, 0, "No image", ""
    pos = detect_head_position(
        img_path, video_w=settings.vertical_width, video_h=settings.vertical_height,
    )
    if pos:
        session_state.scenes[scene_idx].head_pos = pos
        preview = render_head_preview_html(img_path, pos)
        return pos[0], pos[1], f"Detected at ({pos[0]}, {pos[1]})", preview
    preview = render_head_preview_html(img_path, None)
    return 0, 0, "No head detected", preview


def set_manual_head(session_state, scene_idx, x, y):
    """Set head position manually. Returns (status, preview_html)."""
    if session_state is None or scene_idx is None:
        return "No session", ""
    x = max(0, min(int(x), settings.vertical_width))
    y = max(0, min(int(y), settings.vertical_height))
    session_state.scenes[scene_idx].head_pos = (x, y)
    img_path = session_state.scene_img_paths[scene_idx]
    preview = render_head_preview_html(img_path, (x, y))
    return f"Set to ({x}, {y})", preview


def clear_head(session_state, scene_idx):
    """Clear head position. Returns (x, y, status, preview_html)."""
    if session_state is None or scene_idx is None:
        return 0, 0, "No session", ""
    session_state.scenes[scene_idx].head_pos = None
    img_path = session_state.scene_img_paths[scene_idx]
    preview = render_head_preview_html(img_path, None)
    return 0, 0, "Cleared", preview
