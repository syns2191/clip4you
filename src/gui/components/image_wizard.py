"""Step-by-step scene review wizard for the Story tab."""

import os
import gradio as gr

from ..pipeline.story_runner import StorySession, regenerate_scene, pick_variant
from .head_tagger import (
    create_head_controls, auto_detect_head, set_manual_head, clear_head,
    render_head_preview_html,
)


def _scene_summary(session: StorySession, idx: int) -> str:
    n = len(session.scenes)
    markers = []
    for i in range(n):
        if i < idx:
            markers.append(f"~~{i+1}~~")
        elif i == idx:
            markers.append(f"**[{i+1}]**")
        else:
            markers.append(f"{i+1}")
    return " | ".join(markers)


def _scene_info(session: StorySession, idx: int) -> str:
    scene = session.scenes[idx]
    head = scene.head_pos
    head_str = f"({head[0]}, {head[1]})" if head else "none"
    nv = len(session.scene_variants[idx])
    picked = session.scene_img_paths[idx]
    if session.visuals == "gallery":
        pick_label = f"**Picked:** {os.path.basename(picked)}" if picked else "**Picked:** none — click an image below"
        return (
            f"### Scene {idx+1} of {len(session.scenes)}\n\n"
            f"**Text:** {scene.text[:100]}{'...' if len(scene.text) > 100 else ''}\n\n"
            f"**Duration:** {scene.duration:.1f}s | **Head:** {head_str} | **Gallery:** {nv} images\n\n"
            f"{pick_label}"
        )
    return (
        f"### Scene {idx+1} of {len(session.scenes)}\n\n"
        f"**Text:** {scene.text[:100]}{'...' if len(scene.text) > 100 else ''}\n\n"
        f"**Duration:** {scene.duration:.1f}s | **Head:** {head_str} | **Variants:** {nv}"
    )


def _variant_images(session: StorySession, idx: int):
    variants = session.scene_variants[idx]
    if variants:
        return variants
    img = session.scene_img_paths[idx]
    return [img] if img else []


def get_wizard_state(session, idx):
    """Return all display values for the current wizard scene.

    Returns 7 values: (progress, info, gallery, hx, hy, status, head_preview_html)
    """
    if session is None or not session.scenes:
        return "No session", "No scenes", [], 0, 0, "No data", ""
    idx = max(0, min(idx, len(session.scenes) - 1))
    scene = session.scenes[idx]
    hx = scene.head_pos[0] if scene.head_pos else 0
    hy = scene.head_pos[1] if scene.head_pos else 0
    h_status = f"({hx}, {hy})" if scene.head_pos else "none"
    img_path = session.scene_img_paths[idx]
    preview_html = render_head_preview_html(img_path, scene.head_pos)
    return (
        _scene_summary(session, idx),
        _scene_info(session, idx),
        _variant_images(session, idx),
        hx, hy, h_status,
        preview_html,
    )


def on_pick_variant(session, scene_idx, evt: gr.SelectData):
    """When user clicks an image in the gallery, pick that variant."""
    if session is None:
        return session, "No session"
    variant_idx = evt.index
    pick_variant(session, scene_idx, variant_idx)
    scene = session.scenes[scene_idx]
    head_str = f"({scene.head_pos[0]}, {scene.head_pos[1]})" if scene.head_pos else "auto-detected"
    return session, f"Picked variant {variant_idx + 1}. Head: {head_str}"


def on_regenerate(session, scene_idx):
    """Regenerate variants for current scene."""
    if session is None:
        return session, [], "No session"
    regenerate_scene(session, scene_idx)
    return session, _variant_images(session, scene_idx), f"Regenerated scene {scene_idx + 1}"


def on_next(session, scene_idx):
    """Move to next scene."""
    if session is None:
        return 0
    return min(scene_idx + 1, len(session.scenes) - 1)


def on_prev(session, scene_idx):
    """Move to previous scene."""
    return max(scene_idx - 1, 0)
