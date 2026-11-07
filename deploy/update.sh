#!/usr/bin/env bash
# 새 코드 반영: 받기 → 다시 빌드 → 헬스 체크 통과 확인. 실패하면 이전 이미지로 되돌린다.
set -euo pipefail
cd "$(dirname "$0")/.."
PROFILE=${PROFILE:-tunnel}
PREV=$(git rev-parse HEAD)
git pull --ff-only
export AUDITON_VERSION=$(git rev-parse --short HEAD)
sudo -E docker compose --profile "$PROFILE" up -d --build
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then echo "배포 성공: $AUDITON_VERSION"; exit 0; fi
  sleep 3
done
echo "헬스 체크 실패 → $PREV 로 되돌림"
git checkout -q "$PREV"
export AUDITON_VERSION=$(git rev-parse --short HEAD)
sudo -E docker compose --profile "$PROFILE" up -d --build
git checkout -q main
exit 1
