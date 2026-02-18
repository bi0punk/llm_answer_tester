#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH="${MODEL_PATH:-/models/model.gguf}"
ALIAS="${ALIAS:-qwen25}"
PORT="${PORT:-8000}"
CTX="${CTX:-8192}"
THREADS="${THREADS:--1}"
GPU_LAYERS="${GPU_LAYERS:-0}"

echo "[llama] model=${MODEL_PATH} alias=${ALIAS} port=${PORT} ctx=${CTX} threads=${THREADS} gpu_layers=${GPU_LAYERS}"

exec /opt/llama.cpp/build/bin/llama-server   --model "${MODEL_PATH}"   --alias "${ALIAS}"   --port "${PORT}"   --ctx-size "${CTX}"   --threads "${THREADS}"   --n-gpu-layers "${GPU_LAYERS}"
