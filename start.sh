#!/usr/bin/env bash
# Start the Ab Initio → PySpark migration platform.
# Brings up Neo4j, the FastAPI backend, and the Next.js frontend via docker compose,
# then waits until each service is reachable before printing the access URLs.

set -euo pipefail

cd "$(dirname "$0")"

# ── pretty output ─────────────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"; DIM="\033[2m"; RESET="\033[0m"
log()  { printf "${GREEN}▶${RESET} %s\n" "$*"; }
warn() { printf "${YELLOW}!${RESET} %s\n" "$*"; }
err()  { printf "${RED}✗${RESET} %s\n" "$*" >&2; }

# ── pre-flight ────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  err "Docker is not installed. Install Docker Desktop first."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  err "Docker daemon is not running. Start Docker Desktop and retry."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  err "docker compose plugin not found."
  exit 1
fi

# ── parse flags ───────────────────────────────────────────────────────────
REBUILD=0
DETACH=1
LOGS=0
for arg in "$@"; do
  case "$arg" in
    --rebuild|-r) REBUILD=1 ;;
    --foreground|-f) DETACH=0 ;;
    --logs|-l) LOGS=1 ;;
    -h|--help)
      cat <<EOF
Usage: ./start.sh [options]

  -r, --rebuild     Rebuild images before starting (use after code changes)
  -f, --foreground  Run in foreground (Ctrl-C stops everything)
  -l, --logs        Tail logs after services come up
  -h, --help        Show this help

Examples:
  ./start.sh                # start in background, print URLs
  ./start.sh --rebuild      # rebuild and start (after pulling new code)
  ./start.sh --logs         # start and tail combined logs
EOF
      exit 0 ;;
    *) warn "Unknown flag: $arg (use --help)" ;;
  esac
done

# ── bring services up ─────────────────────────────────────────────────────
UP_ARGS=()
[ "$DETACH" -eq 1 ] && UP_ARGS+=(-d)
[ "$REBUILD" -eq 1 ] && UP_ARGS+=(--build)

log "Starting services (neo4j, backend, frontend)..."
$COMPOSE up "${UP_ARGS[@]}"

[ "$DETACH" -eq 0 ] && exit 0   # foreground mode already exited via Ctrl-C

# ── wait for readiness ────────────────────────────────────────────────────
wait_http() {
  local name="$1" url="$2" tries="${3:-60}"
  printf "  ${DIM}waiting for %s${RESET}" "$name"
  for ((i=1; i<=tries; i++)); do
    if curl -fsS -o /dev/null --max-time 2 "$url"; then
      printf "  ${GREEN}✓${RESET}\n"
      return 0
    fi
    printf "."
    sleep 1
  done
  printf "  ${RED}✗${RESET}\n"
  return 1
}

log "Waiting for services to be ready..."
wait_http "Neo4j   " "http://localhost:7474" 60 || warn "Neo4j slow to come up (check: $COMPOSE logs neo4j)"
wait_http "Backend " "http://localhost:8000/docs" 60 || warn "Backend slow to come up (check: $COMPOSE logs backend)"
wait_http "Frontend" "http://localhost:3000" 90 || warn "Frontend slow to come up (check: $COMPOSE logs frontend)"

# ── done ──────────────────────────────────────────────────────────────────
cat <<EOF

${GREEN}All services up.${RESET}

  Frontend   →  http://localhost:3000
  Backend    →  http://localhost:8000/docs
  Neo4j UI   →  http://localhost:7474     (neo4j / password)

Useful commands:
  $COMPOSE logs -f                # tail all logs
  $COMPOSE logs -f backend        # tail one service
  $COMPOSE ps                     # service status
  $COMPOSE down                   # stop everything

EOF

[ "$LOGS" -eq 1 ] && exec $COMPOSE logs -f
