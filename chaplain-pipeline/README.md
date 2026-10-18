# Trading Chaplain Pipeline

Claude writes a 45–60 second video script, then ElevenLabs turns it into a voiceover MP3.

## Setup

1. **Get a Claude API key:** sign in at [platform.claude.com](https://platform.claude.com), add billing under **Settings → Billing**, then create a key under **Settings → API Keys**. Create it inside a workspace so it starts with `sk-ant-api`. Copy it right away; it's only shown once. If your key starts with `sk-ant-usr-`, also set `ANTHROPIC_WORKSPACE_ID` in `.env`.
2. **Get an ElevenLabs API key:** in your ElevenLabs dashboard, open your profile and go to **API Keys**.
3. **Install and configure:**

   ```bash
   cd chaplain-pipeline
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -U -r requirements.txt
   cp .env.example .env    # then paste both keys into .env
   ```

`.env` is in `.gitignore`, so your keys never get committed.

## Run

```bash
python pipeline.py "PILLAR E: Grief that shows up on an ordinary Tuesday"
```

With no topic it uses a default Pillar A topic. Each run writes two files to `output/`:

- `chaplain_daily_xxxxxx.mp3`: the voiceover (hook + script)
- `chaplain_daily_xxxxxx.json`: the script, B-roll search query, and caption style

## Customizing

- **Persona and rules:** edit `system_prompt.xml`.
- **Voice:** set `ELEVENLABS_VOICE_ID` in `.env`.
- **Model:** change `CLAUDE_MODEL` in `pipeline.py`. `claude-sonnet-5-5` costs about half as much and works well for short scripts.
