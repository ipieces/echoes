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

## Quick Start

```bash
# Install dependencies
uv sync

# Download ASR models (optional, for local processing)
uv run python scripts/download_models.py

# Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your settings

# Start watching for audio files
uv run audio-journal start

# Or process a single file
uv run audio-journal process recording.wav

# View archived entries
uv run audio-journal list
uv run audio-journal show <id>
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
