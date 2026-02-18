# Bench Llama.cpp (API + Cliente) en Docker

Este proyecto levanta:
- `llama` : llama.cpp `llama-server` (endpoint OpenAI-compatible)
- `api`   : API que recibe prompts por HTTP, ejecuta contra llama.cpp, guarda resultados (SQLite + JSONL)
- `client`: envía prompts (batch) a la API y hace polling hasta terminar

## 1) Requisito: poner el modelo GGUF
Copia tu modelo a:

- `./models/model.gguf`

(Alternativa: cambia `MODEL_PATH` en `docker-compose.yml`.)

## 2) Levantar servicios

```bash
docker compose build
docker compose up -d
```

Health:
- Llama: `http://127.0.0.1:8000/health`
- API:   `http://127.0.0.1:8080/health`

## 3) Ejecutar un batch con el cliente

Edita `./prompts/prompts.txt` y luego:

```bash
docker compose run --rm client --server http://api:8080 --prompts /prompts/prompts.txt --stream
```

## 4) Ver resultados

Persisten en:
- `./data/bench.db`
- `./data/results.jsonl`

Para obtener un run específico:
- `GET http://127.0.0.1:8080/runs/<run_id>`
- `GET http://127.0.0.1:8080/runs/<run_id>/results`

## 5) Endpoints principales

- `POST /batch`  -> encola prompts y devuelve run_id
- `GET  /runs/{run_id}` -> estado/progreso
- `GET  /runs/{run_id}/results` -> resultados
- `POST /ask` -> 1 prompt, responde inmediato y guarda
