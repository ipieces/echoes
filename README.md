# Echoes

**Echoes** is an intelligent audio journaling system that automatically captures, transcribes, and analyzes your daily conversations. Wear a recording device throughout your day, and Echoes transforms hours of audio into structured, searchable insights.

## What It Does

Echoes watches for new audio files, then automatically:
- Splits long recordings into manageable chunks
- Transcribes speech with speaker identification (local ASR)
- Segments conversations by topic and silence
- Classifies scenes (meetings, calls, ideas, learning, business, casual chat)
- Extracts key insights using AI analysis
- Archives everything as searchable markdown with metadata

## Key Features

- **Fully Automated**: Drop audio files in a folder, get structured notes out
- **Privacy-First**: Local ASR processing, your audio never leaves your machine
- **Multi-Scene Analysis**: Different AI prompts for meetings, business calls, brainstorming, and more
- **Smart Archiving**: Organized by date and scene, with JSONL indexing for fast queries
- **CLI Management**: Simple commands to view, search, and reprocess your audio journal

## Installation

### 1. Install Dependencies

```bash
# Clone the repository
git clone https://github.com/ipieces/echoes.git
cd echoes

# Install Python dependencies with uv
uv sync

# Install FunASR dependencies (for real ASR)
uv pip install funasr modelscope torch torchaudio
```

### 2. Download ASR Models

FunASR requires 4 models (~2GB total). Run the download script:

```bash
uv run python scripts/download_funasr_models.py
```

This downloads:
- `paraformer-zh` (ASR model, ~857MB)
- `fsmn-vad` (Voice Activity Detection)
- `ct-punc` (Punctuation restoration)
- `cam++` (Speaker diarization)

Models are saved to `models/` directory (excluded from git).

### 3. Configure

```bash
# Copy example config
cp config.yaml.example config.yaml

# Edit config.yaml with your settings:
# - Set LLM API keys (DEEPSEEK_API_KEY, ZHIPUAI_API_KEY, etc.)
# - Configure ASR engine (mock or funasr)
# - Adjust paths and processing parameters
```

### 4. Set Environment Variables

```bash
# For LLM API access
export DEEPSEEK_API_KEY="your-key-here"
# or
export ZHIPUAI_API_KEY="your-key-here"

# For mock ASR testing (optional)
export AUDIO_JOURNAL_MOCK_ASR_FIXTURE="test_data/fixture_meeting.json"
```

## Quick Start

```bash
# Process a single audio file
uv run audio-journal process recording.wav

# Start file watcher (auto-process new files)
uv run audio-journal start

# Daily batch processing (merge all files from a date)
uv run audio-journal batch --date 2026-03-01
uv run audio-journal batch-all  # Process all dates in inbox

# View archived entries
uv run audio-journal list
uv run audio-journal list --date 2026-03-01
uv run audio-journal list --scene meeting
uv run audio-journal show <id>

# Check status
uv run audio-journal status
```

## Architecture

```
File Watcher → Audio Chunker → ASR + Speaker ID → Segmenter → 
Scene Classifier → Scene-Specific Analyzer → Auto Archive
```

## Built With

Python • FunASR • OpenAI-compatible LLMs (DeepSeek/OpenAI/GLM) • Click • Pydantic

---

**Echoes**: Let every moment resonate.
