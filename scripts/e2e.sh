#!/usr/bin/env bash
# End-to-end tests: start a throwaway app container with temp data/inbox, run Playwright, clean up.
# Usage: scripts/e2e.sh <app-image> <playwright-image> <uid:gid>
set -euo pipefail

APP_IMAGE="$1"
PW_IMAGE="$2"
UIDGID="$3"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
NET="et-e2e-$$"
APP="et-e2e-app-$$"

cleanup() {
  docker rm -f "$APP" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

mkdir -p "$WORK/data" "$WORK/inbox/faturas" "$WORK/inbox/extratos" "$WORK/profiles" "$WORK/fixtures"
cp "$ROOT"/profiles/examples/*.yaml "$WORK/profiles/"
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
  -e BASE_URL="http://$APP:8080" -e INBOX_DIR=/inbox -e FIXTURES_DIR=/fixtures \
  -v "$ROOT:/src" -v "$WORK/inbox:/inbox" -v "$WORK/fixtures:/fixtures:ro" \
  -w /src/frontend "$PW_IMAGE" \
  npx playwright test --config e2e/playwright.config.ts
