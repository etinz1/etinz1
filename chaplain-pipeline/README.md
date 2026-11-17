# Trading Chaplain Pipeline

Claude writes a 45–60 second video script, ElevenLabs turns it into a voiceover, and the pipeline builds a finished vertical video with stock B-roll and synced captions.

## Setup

1. **Get a Claude API key:** sign in at [platform.claude.com](https://platform.claude.com), add billing under **Settings → Billing**, then create a key under **Settings → API Keys**. Create it inside a workspace so it starts with `sk-ant-api`. Copy it right away; it's only shown once. If your key starts with `sk-ant-usr-`, also set `ANTHROPIC_WORKSPACE_ID` in `.env`.
2. **Get an ElevenLabs API key:** in your ElevenLabs dashboard, open your profile and go to **API Keys**.
3. **Get a free Pexels API key** at [pexels.com/api](https://www.pexels.com/api/) for the stock footage. Without it, everything but the video step still works.
4. **Install and configure:**

   ```bash
   cd chaplain-pipeline
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -U -r requirements.txt
   cp .env.example .env    # then paste your keys into .env
   ```

`.env` is in `.gitignore`, so your keys never get committed.

## Run

```bash
python pipeline.py "PILLAR E: Grief that shows up on an ordinary Tuesday"
```

With no topic it uses a default Pillar A topic. Each run writes three files to `output/`:

- `chaplain_daily_xxxxxx.mp4`: the finished 1080x1920 video, ready to post
- `chaplain_daily_xxxxxx.mp3`: the voiceover (hook + script)
- `chaplain_daily_xxxxxx.json`: the script, B-roll search query, caption style, word timings and Pexels credits

## Write now, voice later

On a network that blocks ElevenLabs (but not Claude), save scripts only, then make all the MP3s later:

```bash
python pipeline.py --script-only "PILLAR D: What shalom really means"
python pipeline.py --script-only --topics-file topics.txt   # one topic per line
python pipeline.py --voice-pending                          # later, on another network
python pipeline.py --video-pending                          # then make the videos
```

`--voice-pending` voices every saved script in `output/` that doesn't have an MP3 yet. `--video-pending` makes a video for every voiced script that doesn't have one yet. Rendering takes a minute or two per video.

## Customizing

- **Captions:** the colour comes from each script's `caption_style` (yellow, gold, red, cream, ...), white by default. Size, position and words per caption are at the top of `video.py`. Set `CAPTION_FONT` in `.env` to a `.ttf` path to change the font.

- **Persona and rules:** edit `system_prompt.xml`.
- **Voice:** set `ELEVENLABS_VOICE_ID` in `.env`.
- **Model:** change `CLAUDE_MODEL` in `pipeline.py`. `claude-sonnet-5-5` costs about half as much and works well for short scripts.
