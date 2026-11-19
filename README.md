# FilmSpottingBot

**English** | [Español](README.es.md)

Generate high-quality, artifact-free stills from your local library of movies, series and anime: with subtitles, format changes, side-by-side comparisons between scenes or movies, and short GIF/MP4 clips. Use it through **CLI-style commands** or in **natural language** (a LangGraph agent on Gemini via Vertex AI, Claude or a local model, traced with LangSmith).

**Live demo:** [filmspotting-988884635912.us-central1.run.app](https://filmspotting-988884635912.us-central1.run.app/docs), deployed on Cloud Run with Gemini on Vertex AI (demo library: *Sintel* and *Big Buck Bunny*). Try `POST /chat` with `{"message": "the frame from Sintel where she says 'a dragon', vertical, Spanish subtitles"}`.

**Design:** the model never touches the media. It only translates intent into a typed Pydantic command (the same schema the CLI uses), and a deterministic executor renders it, so a wrong guess can't produce a broken file. Ambiguous requests pause for the user instead of guessing.

```
CLI / POST /command ──parser──┐
                              ├──▶ Command (Pydantic) ──▶ executor ──▶ ffmpeg / Pillow
POST /chat ──LangGraph + LLM──┘        (the AI only translates intent → command)
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

## Gemini (Google AI Studio or Vertex AI)

```bash
# Gemini API (AI Studio key)
FILMSPOTTING_PROVIDER=google GOOGLE_API_KEY=... uv run filmspotting ask "frame from Akira at 40:10, square"

# Vertex AI (Application Default Credentials)
gcloud auth application-default login
FILMSPOTTING_PROVIDER=google FILMSPOTTING_GOOGLE_VERTEXAI=true FILMSPOTTING_GOOGLE_PROJECT=my-project \
  uv run filmspotting ask "frame from Akira at 40:10, square"
```

Change the model with `FILMSPOTTING_GOOGLE_MODEL` (default `gemini-3.5-flash`) and the Vertex region with `FILMSPOTTING_GOOGLE_LOCATION` (default `global`).

## Deploy to Cloud Run

`deploy/cloudrun.sh` builds the image with Cloud Build (no local Docker needed) and deploys the API with Gemini on **Vertex AI**: no API keys, the service account only gets `roles/aiplatform.user` and read access to the library bucket. Videos live in a Cloud Storage bucket mounted at `/library` and are indexed on startup.

```bash
gcloud auth login
PROJECT=my-project BUCKET=my-filmspotting-library deploy/cloudrun.sh
gcloud storage cp -r ./clips gs://my-filmspotting-library/   # then POST /library/scan
```

Optional: `MODEL`, `FALLBACK_MODEL` (Gemini model to fail over to on 503/429), `REGION` (default `us-central1`). It runs with `--max-instances 1`, so conversation threads (SQLite) stay on one instance; they reset when it scales to zero.

The public demo uses clips from *Sintel* and *Big Buck Bunny*, © Blender Foundation, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) ([durian.blender.org](https://durian.blender.org), [peach.blender.org](https://peach.blender.org)).

## Free local LLM (Ollama)

The CLI and `/command` need no LLM at all. For natural language without an API key, use [Ollama](https://ollama.com):

```bash
brew install ollama && ollama serve        # or the Ollama desktop app
ollama pull qwen2.5:7b                     # ~4.7 GB, needs ~8 GB of RAM
uv sync --extra ollama
FILMSPOTTING_PROVIDER=ollama uv run filmspotting ask "frame from Akira at 40:10, square"
```

Change the model with `FILMSPOTTING_OLLAMA_MODEL` (any model with tool calling, e.g. `llama3.1:8b`, `qwen2.5:14b`). Small local models pick tools and arguments less reliably than Claude; compare them with the LangSmith eval below.

## Image quality

Accurate seeking and lossless PNG output; picks the sharpest frame (variance of the Laplacian) within the same shot around the timestamp; `bwdif` deinterlacing; correct color matrix (BT.709/601) and high-precision chroma conversion; anamorphic pixel correction; HDR→SDR tonemapping (`zscale` + `hable`); `.ass` subtitles rendered with libass, keeping their styling.

## AI

- **LangChain**: `ChatAnthropic` by default (`claude-opus-5-5`, set with `FILMSPOTTING_MODEL` / `FILMSPOTTING_EFFORT`, server-side refusal fallback enabled) `ChatGoogleGenerativeAI` (Gemini API or Vertex AI) with `FILMSPOTTING_PROVIDER=google`, or `ChatOllama` with `FILMSPOTTING_PROVIDER=ollama`. Tool schemas are the same Pydantic models the CLI uses.
- **LangGraph**: agent↔tools loop, `ask_user` with `interrupt()` to resolve ambiguity, and a SQLite checkpointer for follow-ups ("now without subtitles").
- **LangSmith**: with `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`, every `/chat` request is traced. `uv run python evals/langsmith_dataset.py anthropic google ollama` creates the natural-language→command dataset, runs one experiment per provider and prints a comparison table (tool accuracy and argument accuracy). Without `LANGSMITH_API_KEY` it runs the same eval locally.

## Evaluation

`evals/langsmith_dataset.py` scores natural language → tool call on 9 hand-written requests (Spanish and English): right tool, right arguments, and extra lookups (model round trips spent on `search_library` before acting). Results on Gemini via Vertex AI and a local model (Nov 2026):

| Model | System prompt | Correct tool | Correct args | Extra lookups / request |
|---|---|---|---|---|
| gemini-3.5-flash (Vertex AI) | before | 89% | 78% | 1.22 |
| gemini-3.5-flash (Vertex AI) | after | 89% | 78% | 0.44 |
| qwen2.5:7b (Ollama, local) | after | 100% | 100% | 0.00 |

What the eval caught along the way:
- **Outages scored as 0%.** The first run on the free Gemini API hit 503s and quota 429s and reported 0% accuracy. API errors are now counted separately from model quality, and the agent fails over to `FILMSPOTTING_GOOGLE_FALLBACK_MODEL`.
- **The eval was too strict.** Gemini looks a title up before rendering and then refers to it by `media_id`. Scoring only the first call (22% at first) penalized a valid strategy, so the eval now scores the final action and reports lookups as a cost metric instead.
- **The prompt was too loose.** Gemini searched before almost every request. Stating that the render tools resolve titles and quotes themselves cut extra calls by about 3× with no loss in accuracy.

Still failing on Gemini: "the Breaking Bad scene from S05E14…" becomes a clip without season or episode, and "which movie says…?" sometimes ends in a title lookup instead of the quote search. With 9 examples, one case moves a score by 11 points: the next step is growing the dataset from real `/chat` traces before drawing conclusions between models.

## Tests

```bash
uv run pytest      # generates a synthetic clip with ffmpeg; agent tests use a scripted model
```
