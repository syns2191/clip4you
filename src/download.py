"""
Optional: download a YouTube video by URL via yt-dlp, so the pipeline can
accept a pasted link the same way StoryHero's landing page describes
("paste a link into storyhero").
"""
import glob
import os
import subprocess


def download_youtube(url: str, output_path: str = "input.mp4") -> str:
    if os.path.exists(output_path):
        return output_path

    abs_output = os.path.abspath(output_path)
    stem, _ = os.path.splitext(abs_output)
    template = stem + ".%(ext)s"

    subprocess.run(
        [
            "yt-dlp",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--no-part",
            "-o", template,
            url,
        ],
        check=True,
    )

    matches = glob.glob(stem + ".*")
    if not matches:
        raise FileNotFoundError(
            f"yt-dlp ran successfully but no file matching '{stem}.*' was found."
        )

    actual = matches[0]
    if actual != abs_output:
        os.rename(actual, abs_output)

    return abs_output
