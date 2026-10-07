# FilmSpottingBot

[English](README.md) | **Español**

Genera fotogramas de calidad (sin artefactos) de tu biblioteca local de películas, series y anime: con subtítulos, cambios de formato, comparativas entre escenas/películas y GIF/MP4 cortos. Se usa por **comandos tipo CLI** o en **lenguaje natural** (Claude vía LangChain + LangGraph, trazado con LangSmith).

```
CLI / POST /command ──parser──┐
                              ├──▶ Command (Pydantic) ──▶ executor ──▶ ffmpeg / Pillow
POST /chat ──LangGraph+Claude─┘        (la IA solo traduce intención → comando)
```

## Requisitos

- Python 3.11+ y [uv](https://docs.astral.sh/uv/)
- ffmpeg con **libass** (subtítulos) y **zimg** (tonemapping HDR). En macOS: `brew install ffmpeg-full` (se detecta automáticamente). Sin ellos, los subtítulos se dibujan con Pillow y el HDR no se tonemapea.

```bash
uv sync
cp .env.example .env   # FILMSPOTTING_LIBRARY_DIR, ANTHROPIC_API_KEY, LANGSMITH_*
uv run filmspotting scan            # indexa vídeos y subtítulos (.srt/.ass externos y embebidos)
```

## Comandos

```bash
uv run filmspotting frame "Spirited Away@01:12:33" --subs es --aspect 9:16 --mode blur
uv run filmspotting frame "Breaking Bad S05E14" --quote "i am the one who knocks" --lang en
uv run filmspotting compare "Akira@00:40:10" "Ghost in the Shell@00:05:00" --layout vertical
uv run filmspotting clip "Totoro" --at 00:20:00 --duration 4 --subs en        # GIF (--mp4 para vídeo)
uv run filmspotting search "evangelion"            # títulos
uv run filmspotting search "que la fuerza" --quotes # frases en subtítulos
uv run filmspotting ask "la escena de Chihiro en el tren, en vertical con subs en español"
```

Formato de fuente: `"Título [SxxEyy][@timestamp|@frase]"` o `"#<id>@..."`. Opciones de estilo: `--subs LANG|auto`, `--caption TEXTO`, `--caption-pos bottom|top|center`, `--aspect 16:9|9:16|1:1|4:5|21:9`, `--mode crop|pad|blur`, `--width N`, `--format png|jpg|webp`, `--exact` (frame exacto en vez del más nítido).

## API

`uv run filmspotting serve` → http://127.0.0.1:8000/docs

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/command` | `{"cmd": "frame \"Akira@00:40:10\" --aspect 1:1"}` |
| POST | `/command/structured` | El mismo comando en JSON |
| POST | `/chat` | `{"message": "...", "thread_id": "opcional"}` → `reply`, `files` o `question`+`options` |
| POST | `/chat/{thread_id}/resume` | `{"answer": "..."}` para responder a la pregunta del agente |
| GET | `/media/search?q=...&quotes=true` | Búsqueda |
| POST | `/library/scan` | Re-indexar |
| GET | `/outputs/{name}` | Descarga del resultado |

## Calidad de imagen

Seek preciso y PNG sin pérdida; elige el fotograma más nítido (varianza del Laplaciano) dentro del mismo plano alrededor del timestamp; desentrelazado `bwdif`; matriz de color correcta (BT.709/601) y conversión de croma de alta precisión; corrección de píxel anamórfico; tonemapping HDR→SDR (`zscale`+`hable`); subtítulos `.ass` con libass conservando estilos.

## IA

- **LangChain**: `ChatAnthropic` (`claude-opus-5-5` por defecto, `FILMSPOTTING_MODEL` / `FILMSPOTTING_EFFORT`) con tools cuyo esquema son los mismos modelos Pydantic de la CLI. Fallback de rechazos del lado del servidor activado.
- **LangGraph**: bucle agente↔tools, `ask_user` con `interrupt()` para desambiguar, checkpointer SQLite para seguimientos ("ahora sin subtítulos").
- **LangSmith**: con `LANGSMITH_TRACING=true` y `LANGSMITH_API_KEY` todo `/chat` queda trazado. `uv run python evals/langsmith_dataset.py` crea el dataset NL→comando y lanza la evaluación (hace una llamada a Claude por ejemplo).

## Tests

```bash
uv run pytest      # genera un clip sintético con ffmpeg; los tests del agente usan un modelo simulado
```
