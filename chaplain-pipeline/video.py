"""Turns a voiced script into a vertical MP4: stock B-roll, synced captions, voiceover."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import requests
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT, FPS = 1080, 1920, 30
WORDS_PER_CAPTION = 3
SECONDS_PER_CLIP = 6
CLIPS_PER_VIDEO = 5
CAPTION_FONT_SIZE = 92
CAPTION_Y = int(HEIGHT * 0.60)
PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
FALLBACK_QUERY = "calm nature light"

FONT_CANDIDATES = [
    os.environ.get("CAPTION_FONT"),
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

# Picked from Claude's free-text caption_style, e.g. "Bold yellow, single words".
CAPTION_COLORS = {
    "yellow": (255, 214, 0),
    "gold": (232, 184, 74),
    "orange": (255, 149, 0),
    "red": (235, 64, 52),
    "green": (80, 200, 120),
    "blue": (90, 170, 255),
    "cream": (245, 235, 215),
    "white": (255, 255, 255),
}


def words_from_alignment(alignment):
    """Groups ElevenLabs character timings into [{"word", "start", "end"}]."""
    words, current = [], None
    for char, start, end in zip(
        alignment.characters,
        alignment.character_start_times_seconds,
        alignment.character_end_times_seconds,
    ):
        if char.isspace():
            if current:
                words.append(current)
                current = None
        elif current is None:
            current = {"word": char, "start": start, "end": end}
        else:
            current["word"] += char
            current["end"] = end
    if current:
        words.append(current)
    return words


def estimate_words(text, duration):
    """Spreads words over the audio by length, for voiceovers made without timings."""
    tokens = text.split()
    total = sum(len(t) + 1 for t in tokens)
    words, t = [], 0.0
    for token in tokens:
        span = duration * (len(token) + 1) / total
        words.append({"word": token, "start": t, "end": t + span})
        t += span
    return words


def caption_color(caption_style):
    style = (caption_style or "").lower()
    for name, rgb in CAPTION_COLORS.items():
        if name in style:
            return rgb
    return CAPTION_COLORS["white"]


def load_font():
    for path in FONT_CANDIDATES:
        if path and Path(path).exists():
            return ImageFont.truetype(path, CAPTION_FONT_SIZE)
    return ImageFont.load_default(size=CAPTION_FONT_SIZE)


def render_caption(text, font, color):
    """Draws one caption as a transparent image, wrapped to fit the frame."""
    max_width = WIDTH - 140
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and draw.textlength(trial, font=font) > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)

    stroke = 8
    line_height = CAPTION_FONT_SIZE + 24
    image = Image.new("RGBA", (WIDTH, line_height * len(lines) + stroke * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for i, text_line in enumerate(lines):
        x = (WIDTH - draw.textlength(text_line, font=font)) / 2
        draw.text((x, stroke + i * line_height), text_line, font=font, fill=color,
                  stroke_width=stroke, stroke_fill=(0, 0, 0))
    return np.array(image)


def fetch_broll(query, clip_dir):
    """Downloads portrait stock clips from Pexels for the script's visual theme."""
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY is missing from .env")

    short_query = " ".join(query.split()[:2])
    for attempt in dict.fromkeys([query, short_query, FALLBACK_QUERY]):
        response = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": attempt, "orientation": "portrait", "per_page": 15},
            timeout=30,
        )
        response.raise_for_status()
        videos = response.json().get("videos", [])
        if videos:
            break
    else:
        return [], []

    paths, credits = [], []
    for video in videos[:CLIPS_PER_VIDEO]:
        files = [f for f in video["video_files"]
                 if f.get("file_type") == "video/mp4" and f.get("height") and f["height"] >= f["width"]]
        if not files:
            continue
        # Smallest file that's still at least 1280 tall keeps downloads quick.
        tall_enough = [f for f in files if f["height"] >= 1280]
        best = min(tall_enough, key=lambda f: f["height"]) if tall_enough else max(files, key=lambda f: f["height"])

        path = clip_dir / f"clip_{video['id']}.mp4"
        with requests.get(best["link"], stream=True, timeout=120) as download:
            download.raise_for_status()
            with open(path, "wb") as f:
                for chunk in download.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        paths.append(path)
        credits.append({"pexels_url": video.get("url"), "author": video.get("user", {}).get("name")})
    return paths, credits


def fit_vertical(path):
    """Scales a clip to cover 1080x1920 and crops the overflow from the centre.

    Done once up front with ffmpeg, which is far faster than resizing frame by frame.
    """
    fitted = path.with_name(f"fitted_{path.name}")
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-i", str(path),
         "-t", str(SECONDS_PER_CLIP),
         "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},fps={FPS}",
         "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(fitted)],
        check=True,
    )
    return fitted


def build_background(clip_paths, duration):
    if not clip_paths:
        return ColorClip((WIDTH, HEIGHT), color=(18, 18, 24)).with_duration(duration), []

    sources = [VideoFileClip(str(fit_vertical(p)), audio=False) for p in clip_paths]
    segments, t, i = [], 0.0, 0
    while t < duration:
        source = sources[i % len(sources)]
        length = min(SECONDS_PER_CLIP, source.duration, duration - t)
        segments.append(source.subclipped(0, length))
        t += length
        i += 1
    return concatenate_videoclips(segments), sources


def build_captions(words, duration, color):
    font = load_font()
    chunks, chunk = [], []
    for word in words:
        chunk.append(word)
        # Start a fresh caption at each sentence end so lines read naturally.
        if len(chunk) == WORDS_PER_CAPTION or word["word"].endswith((".", "!", "?")):
            chunks.append(chunk)
            chunk = []
    if chunk:
        chunks.append(chunk)
    captions = []
    for n, chunk in enumerate(chunks):
        start = chunk[0]["start"]
        # Hold each caption until the next one starts, so the screen never flickers empty.
        end = chunks[n + 1][0]["start"] if n + 1 < len(chunks) else duration
        if end <= start:
            continue
        text = " ".join(w["word"] for w in chunk)
        captions.append(
            ImageClip(render_caption(text, font, color))
            .with_start(start)
            .with_duration(end - start)
            .with_position(("center", CAPTION_Y))
        )
    return captions


def make_video(video_data, audio_path, out_path):
    """Renders the finished vertical video. Returns Pexels credits for the clips used."""
    audio = AudioFileClip(str(audio_path))
    duration = audio.duration
    spoken_text = f"{video_data['hook']} {video_data['script']}"
    words = video_data.get("words") or estimate_words(spoken_text, duration)

    clip_dir = Path(tempfile.mkdtemp(prefix="broll_"))
    sources = []
    try:
        print(f"🎞️ Finding B-roll for: {video_data['visual_theme']}")
        clip_paths, credits = fetch_broll(video_data["visual_theme"], clip_dir)
        background, sources = build_background(clip_paths, duration)
        # Darken the footage so captions stay readable on bright clips.
        shade = ColorClip((WIDTH, HEIGHT), color=(0, 0, 0)).with_opacity(0.35).with_duration(duration)
        captions = build_captions(words, duration, caption_color(video_data.get("caption_style")))

        final = (CompositeVideoClip([background, shade, *captions], size=(WIDTH, HEIGHT))
                 .with_duration(duration)
                 .with_audio(audio))
        print("🎬 Rendering video (this takes a minute or two)...")
        final.write_videofile(str(out_path), fps=FPS, codec="libx264", audio_codec="aac",
                              preset="medium", threads=4)
        final.close()
        return credits
    finally:
        audio.close()
        for source in sources:
            source.close()
        shutil.rmtree(clip_dir, ignore_errors=True)
