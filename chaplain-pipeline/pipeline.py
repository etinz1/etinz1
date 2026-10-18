"""Daily Trading Chaplain pipeline: Claude writes the script, ElevenLabs voices it.

Usage:
    python pipeline.py "PILLAR A: The spiritual root of revenge trading"
"""

import os
import sys
import json
import uuid
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

for key in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY"):
    if not os.environ.get(key):
        sys.exit(f"❌ {key} is missing. Copy .env.example to .env and add your key.")

# Reads ANTHROPIC_API_KEY from the environment. Keys not scoped to a workspace
# (sk-ant-usr-...) must also name a workspace via ANTHROPIC_WORKSPACE_ID.
workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
claude_client = anthropic.Anthropic(
    default_headers={"anthropic-workspace-id": workspace_id} if workspace_id else None
)
elevenlabs_client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

CLAUDE_MODEL = "claude-opus-5-5"
# "Adam" (deep, authoritative). Swap for any Voice ID from your ElevenLabs dashboard.
VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
OUTPUT_DIR = BASE_DIR / "output"
MAX_WORDS = 120
DEFAULT_TOPIC = "PILLAR A: The spiritual root of revenge trading and moving your stop loss."

system_prompt = (BASE_DIR / "system_prompt.xml").read_text()


class VideoScript(BaseModel):
    pillar_used: str
    hook: str
    script: str
    visual_theme: str
    caption_style: str


def generate_daily_script(topic):
    """Uses Claude to generate the video script and metadata."""
    print(f"🧠 Generating Trading Chaplain script for: {topic}...\n")

    try:
        response = claude_client.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=16000,  # room for thinking + the JSON
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"Write today's script. The topic is: {topic}"}
            ],
            output_format=VideoScript,  # guarantees schema-valid JSON
        )
    except anthropic.AuthenticationError:
        print("❌ Claude rejected the API key. Check ANTHROPIC_API_KEY in .env.")
        return None
    except anthropic.RateLimitError:
        print("❌ Claude rate limit hit. Try again in a minute.")
        return None
    except anthropic.APIStatusError as e:
        print(f"❌ Claude API error {e.status_code}: {e.message}")
        return None
    except anthropic.APIConnectionError:
        print("❌ Could not reach the Claude API.")
        return None

    if response.stop_reason == "refusal":
        print("❌ Claude declined this topic. Try rephrasing it.")
        return None
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        print("❌ Claude's output was cut off. Raise max_tokens.")
        return None

    script_data = response.parsed_output.model_dump()
    word_count = len(f"{script_data['hook']} {script_data['script']}".split())

    print("✅ Script Generated Successfully!")
    print(f"Hook: {script_data['hook']}")
    print(f"Spoken words: {word_count}")
    if word_count > MAX_WORDS:
        print(f"⚠️ Over the {MAX_WORDS}-word limit. Video may run past 60 seconds.")

    return script_data


def generate_voiceover(text, save_path):
    """Uses ElevenLabs to generate an MP3 from the script."""
    print("🎙️ Sending script to ElevenLabs...")

    try:
        audio_stream = elevenlabs_client.text_to_speech.convert(
            voice_id=VOICE_ID,
            output_format="mp3_44100_128",
            text=text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=0.5,        # lower = more emotive/pastoral delivery
                similarity_boost=0.75,
            ),
        )
        with open(save_path, "wb") as f:
            for chunk in audio_stream:
                if chunk:
                    f.write(chunk)

        print(f"✅ Voiceover saved to: {save_path}\n")
        return save_path

    except Exception as e:
        print(f"❌ ElevenLabs Error: {e}")
        Path(save_path).unlink(missing_ok=True)  # don't leave a half-written MP3
        return None


if __name__ == "__main__":
    todays_topic = " ".join(sys.argv[1:]) or DEFAULT_TOPIC

    video_data = generate_daily_script(todays_topic)
    if not video_data:
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    run_id = f"chaplain_daily_{uuid.uuid4().hex[:6]}"

    # Hook is the spoken opener, so it leads the voiceover.
    spoken_text = f"{video_data['hook']} {video_data['script']}"
    audio_file = generate_voiceover(spoken_text, OUTPUT_DIR / f"{run_id}.mp3")

    # Save metadata for the B-roll + captions step.
    video_data["topic"] = todays_topic
    video_data["audio_file"] = str(audio_file) if audio_file else None
    metadata_path = OUTPUT_DIR / f"{run_id}.json"
    with open(metadata_path, "w") as f:
        json.dump(video_data, f, indent=2)
    print(f"📝 Metadata saved to: {metadata_path}")
