#!/usr/bin/env bash
# Visual tour: throwaway app container with synthetic data, Playwright screenshots of every screen
# (light and dark) into OUT_DIR (outside the repo). Fails on console errors or API 5xx.
# Usage: scripts/ui-tour.sh <app-image> <playwright-image> <uid:gid> <out-dir>
set -euo pipefail

APP_IMAGE="$1"
PW_IMAGE="$2"
UIDGID="$3"
OUT="$4"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
NET="et-tour-$$"
APP="et-tour-app-$$"

cleanup() {
  docker rm -f "$APP" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

rm -rf "$OUT"
mkdir -p "$OUT" "$WORK/data" "$WORK/inbox/faturas" "$WORK/inbox/extratos" "$WORK/profiles" "$WORK/fixtures"
docker run --rm -u "$UIDGID" -e HOME=/tmp -v "$ROOT:/src:ro" -v "$WORK/fixtures:/out" \
  expense-tracker-backend-dev python /src/scripts/e2e_fixtures.py /out
echo '{}' > "$WORK/secrets.yaml"
chmod -R a+rwX "$WORK"

docker network create "$NET" >/dev/null
docker run -d --name "$APP" --network "$NET" -u "$UIDGID" \
  -e SCAN_INTERVAL_SECONDS=2 \
  -e ALLOWED_HOSTS="$APP" \
  -v "$WORK/data:/app/data" -v "$WORK/inbox:/app/inbox" -v "$WORK/profiles:/app/profiles" \
  -v "$WORK/secrets.yaml:/run/secrets/pdf-passwords.yaml:ro" \
  --read-only --tmpfs /tmp "$APP_IMAGE" >/dev/null

for _ in $(seq 1 60); do
  if docker run --rm --network "$NET" curlimages/curl:8.11.1 -fsS "http://$APP:8080/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker run --rm --network "$NET" -u "$UIDGID" -e HOME=/tmp \
  -e BASE_URL="http://$APP:8080" -e INBOX_DIR=/inbox -e FIXTURES_DIR=/fixtures -e SHOTS_DIR=/shots \
  -v "$ROOT:/src" -v "$WORK/inbox:/inbox" -v "$WORK/fixtures:/fixtures:ro" -v "$OUT:/shots" \
  -w /src/frontend "$PW_IMAGE" \
  npx playwright test --config e2e/tour/tour.config.ts

echo "screenshots in $OUT"
