# FilmSpottingBot

**English** | [Español](README.es.md)

Generate high-quality, artifact-free stills from your local library of movies, series and anime: with subtitles, format changes, side-by-side comparisons between scenes or movies, and short GIF/MP4 clips. Use it through **CLI-style commands** or in **natural language** (Claude via LangChain + LangGraph, traced with LangSmith).

```
CLI / POST /command ──parser──┐
                              ├──▶ Command (Pydantic) ──▶ executor ──▶ ffmpeg / Pillow
POST /chat ──LangGraph+Claude─┘        (the AI only translates intent → command)
```

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- ffmpeg with **libass** (subtitles) and **zimg** (HDR tonemapping). On macOS: `brew install ffmpeg-full` (detected automatically). Without them, subtitles are drawn with Pillow and HDR sources are not tonemapped.

```bash
uv sync
cp .env.example .env   # FILMSPOTTING_LIBRARY_DIR, ANTHROPIC_API_KEY, LANGSMITH_*
uv run filmspotting scan            # index videos and subtitles (external and embedded .srt/.ass)
```

## Commands

```bash
uv run filmspotting frame "Spirited Away@01:12:33" --subs es --aspect 9:16 --mode blur
uv run filmspotting frame "Breaking Bad S05E14" --quote "i am the one who knocks" --lang en
uv run filmspotting compare "Akira@00:40:10" "Ghost in the Shell@00:05:00" --layout vertical
uv run filmspotting clip "Totoro" --at 00:20:00 --duration 4 --subs en        # GIF (--mp4 for video)
uv run filmspotting search "evangelion"             # titles
uv run filmspotting search "may the force" --quotes # lines in subtitles
uv run filmspotting ask "the train scene from Spirited Away, vertical, with Spanish subs"
```

Source format: `"Title [SxxEyy][@timestamp|@quote]"` or `"#<id>@..."`. Style options: `--subs LANG|auto`, `--caption TEXT`, `--caption-pos bottom|top|center`, `--aspect 16:9|9:16|1:1|4:5|21:9`, `--mode crop|pad|blur`, `--width N`, `--format png|jpg|webp`, `--exact` (the exact frame instead of the sharpest nearby one).

## API

`uv run filmspotting serve` → http://127.0.0.1:8000/docs

| Method | Path | Description |
|---|---|---|
| POST | `/command` | `{"cmd": "frame \"Akira@00:40:10\" --aspect 1:1"}` |
| POST | `/command/structured` | The same command as JSON |
| POST | `/chat` | `{"message": "...", "thread_id": "optional"}` → `reply`, `files`, or `question`+`options` |
| POST | `/chat/{thread_id}/resume` | `{"answer": "..."}` to answer the agent's question |
| GET | `/media/search?q=...&quotes=true` | Search |
| POST | `/library/scan` | Re-index the library |
| GET | `/outputs/{name}` | Download a result |

## Image quality

Accurate seeking and lossless PNG output; picks the sharpest frame (variance of the Laplacian) within the same shot around the timestamp; `bwdif` deinterlacing; correct color matrix (BT.709/601) and high-precision chroma conversion; anamorphic pixel correction; HDR→SDR tonemapping (`zscale` + `hable`); `.ass` subtitles rendered with libass, keeping their styling.

## AI

- **LangChain**: `ChatAnthropic` (`claude-opus-5-5` by default, `FILMSPOTTING_MODEL` / `FILMSPOTTING_EFFORT`) with tools whose schemas are the same Pydantic models the CLI uses. Server-side refusal fallback is enabled.
- **LangGraph**: agent↔tools loop, `ask_user` with `interrupt()` to resolve ambiguity, and a SQLite checkpointer for follow-ups ("now without subtitles").
- **LangSmith**: with `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`, every `/chat` request is traced. `uv run python evals/langsmith_dataset.py` creates the natural-language→command dataset and runs the evaluation (one Claude call per example).

## Tests

```bash
uv run pytest      # generates a synthetic clip with ffmpeg; agent tests use a scripted model
```
