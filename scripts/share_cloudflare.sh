#!/usr/bin/env bash
set -euo pipefail

API_PORT=8000
UI_PORT=8501
HOST_ADDRESS="127.0.0.1"
PYTHON_PATH=""
CLOUDFLARED_PATH="cloudflared"
NO_START_APPS=0
DEBUG_MODE=0

usage() {
  cat <<'EOF'
Usage: scripts/share_cloudflare.sh [options]

Options:
  --api-port PORT             FastAPI port. Default: 8000
  --ui-port PORT              Streamlit port. Default: 8501
  --host-address HOST         Bind/listen host. Default: 127.0.0.1
  --python-path PATH          Python executable. Default: repo .venv, then ../.venv
  --cloudflared-path PATH     cloudflared executable. Default: cloudflared
  --no-start-apps             Do not start FastAPI/Streamlit, only open tunnel
  --debug                     Start Streamlit with developer/debug UI enabled
  -h, --help                  Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-port)
      API_PORT="$2"
      shift 2
      ;;
    --ui-port)
      UI_PORT="$2"
      shift 2
      ;;
    --host-address)
      HOST_ADDRESS="$2"
      shift 2
      ;;
    --python-path)
      PYTHON_PATH="$2"
      shift 2
      ;;
    --cloudflared-path)
      CLOUDFLARED_PATH="$2"
      shift 2
      ;;
    --no-start-apps)
      NO_START_APPS=1
      shift
      ;;
    --debug|-debug)
      DEBUG_MODE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

STORAGE_DIR="$REPO_ROOT/storage"
mkdir -p "$STORAGE_DIR"

if [[ -z "$PYTHON_PATH" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_PATH="$REPO_ROOT/.venv/bin/python"
  elif [[ -x "$REPO_ROOT/../.venv/bin/python" ]]; then
    PYTHON_PATH="$REPO_ROOT/../.venv/bin/python"
  else
    PYTHON_PATH="./.venv/bin/python"
  fi
fi

if [[ "$NO_START_APPS" -eq 0 && ! -x "$PYTHON_PATH" ]]; then
  echo "Python venv not found or not executable at $PYTHON_PATH. Create .venv or pass --python-path." >&2
  exit 1
fi

resolve_cloudflared() {
  local requested="$1"
  local candidate

  if [[ "$requested" == */* ]]; then
    if [[ -x "$requested" ]]; then
      printf '%s\n' "$requested"
      return 0
    fi
    if [[ -f "$requested" ]]; then
      echo "cloudflared exists at $requested but is not executable. Run: chmod +x $requested" >&2
      return 1
    fi
  elif candidate="$(command -v "$requested" 2>/dev/null)"; then
    printf '%s\n' "$candidate"
    return 0
  fi

  for candidate in     "$REPO_ROOT/cloudflared"     "$REPO_ROOT/bin/cloudflared"     "$REPO_ROOT/.venv/bin/cloudflared"     "$HOME/.local/bin/cloudflared"     "$HOME/bin/cloudflared"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

if ! CLOUDFLARED_BIN="$(resolve_cloudflared "$CLOUDFLARED_PATH")"; then
  cat >&2 <<EOF
cloudflared not found.

Cloudflared is a standalone binary, not a Python package in .venv.
Install it without sudo, then run this script again:

  mkdir -p bin
  curl -L --output bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x bin/cloudflared
  ./scripts/share_cloudflare.sh --debug --cloudflared-path ./bin/cloudflared

If your machine is ARM64, use cloudflared-linux-arm64 instead of cloudflared-linux-amd64.
EOF
  exit 1
fi

API_URL="http://${HOST_ADDRESS}:${API_PORT}"
UI_URL="http://${HOST_ADDRESS}:${UI_PORT}"
STARTED_PIDS=()
TUNNEL_PID=""

cleanup() {
  if [[ -n "${TUNNEL_PID:-}" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
    kill "$TUNNEL_PID" 2>/dev/null || true
  fi
  for pid in "${STARTED_PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

http_ok() {
  local url="$1"
  local code
  code="$(curl -L -s -o /dev/null -w '%{http_code}' --max-time 5 "$url" || true)"
  [[ "$code" =~ ^[234][0-9][0-9]$ ]]
}

start_managed_process() {
  local name="$1"
  local stdout_path="$2"
  local stderr_path="$3"
  shift 3
  echo "Starting $name..."
  "$@" >"$stdout_path" 2>"$stderr_path" &
  STARTED_PIDS+=("$!")
}

if [[ "$NO_START_APPS" -eq 0 ]]; then
  if ! http_ok "$API_URL/health"; then
    start_managed_process \
      "FastAPI" \
      "$STORAGE_DIR/share_fastapi.log" \
      "$STORAGE_DIR/share_fastapi.err" \
      "$PYTHON_PATH" -m uvicorn src.app:app --host "$HOST_ADDRESS" --port "$API_PORT"
    sleep 8
  fi

  if ! http_ok "$API_URL/health"; then
    echo "FastAPI is not healthy at $API_URL/health. Check storage/share_fastapi.err" >&2
    exit 1
  fi

  if ! http_ok "$UI_URL/_stcore/health"; then
    export API_BASE_URL="$API_URL"
    streamlit_args=(
      "$PYTHON_PATH" -m streamlit run src/frontend/streamlit_app.py
      --server.port "$UI_PORT"
      --server.address "$HOST_ADDRESS"
      --server.headless true
    )
    if [[ "$DEBUG_MODE" -eq 1 ]]; then
      streamlit_args+=(-- -debug)
    fi
    start_managed_process \
      "Streamlit" \
      "$STORAGE_DIR/share_streamlit.log" \
      "$STORAGE_DIR/share_streamlit.err" \
      "${streamlit_args[@]}"
    sleep 8
  fi

  if ! http_ok "$UI_URL/_stcore/health"; then
    echo "Streamlit is not healthy at $UI_URL/_stcore/health. Check storage/share_streamlit.err" >&2
    exit 1
  fi
fi

echo "Opening Cloudflare quick tunnel for $UI_URL ..."
echo "Keep this terminal open. Press Ctrl+C to stop sharing."

TUNNEL_LOG="$STORAGE_DIR/share_cloudflared.log"
TUNNEL_ERR="$STORAGE_DIR/share_cloudflared.err"
rm -f "$TUNNEL_LOG" "$TUNNEL_ERR"

"$CLOUDFLARED_BIN" tunnel --url "$UI_URL" --no-autoupdate >"$TUNNEL_LOG" 2>"$TUNNEL_ERR" &
TUNNEL_PID="$!"

PUBLIC_URL=""
DEADLINE=$((SECONDS + 90))
URL_PATTERN='https://[-a-zA-Z0-9.]+\.trycloudflare\.com'

while [[ $SECONDS -lt $DEADLINE && -z "$PUBLIC_URL" ]]; do
  for path in "$TUNNEL_LOG" "$TUNNEL_ERR"; do
    if [[ -f "$path" ]]; then
      PUBLIC_URL="$(grep -Eo "$URL_PATTERN" "$path" | head -n 1 || true)"
      if [[ -n "$PUBLIC_URL" ]]; then
        break
      fi
    fi
  done

  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "cloudflared exited early." >&2
    tail -n 40 "$TUNNEL_LOG" "$TUNNEL_ERR" 2>/dev/null >&2 || true
    exit 1
  fi

  sleep 0.25
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "Could not find Cloudflare public URL in cloudflared output. Check $TUNNEL_LOG and $TUNNEL_ERR" >&2
  exit 1
fi

echo ""
echo "============================================================"
echo "Share this Streamlit URL with teammates:"
echo "$PUBLIC_URL"
echo "Local UI: $UI_URL"
echo "Local API: $API_URL"
echo "============================================================"
echo ""

wait "$TUNNEL_PID"
