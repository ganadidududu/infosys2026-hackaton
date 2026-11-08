#!/usr/bin/env bash
# 새 코드 반영: 받기 → 다시 빌드 → 헬스 체크 통과 확인. 실패하면 이전 이미지로 되돌린다.
set -euo pipefail
cd "$(dirname "$0")/.."
PROFILE=${PROFILE:-tunnel}
PREV=$(git rev-parse HEAD)
git pull -q --ff-only origin main
export AUDITON_VERSION=$(git rev-parse --short HEAD)
sudo -E docker compose --profile "$PROFILE" up -d --build
for i in $(seq 1 30); do
  # 새 버전 컨테이너가 헬스 체크를 통과해야 성공(이전 컨테이너 응답으로 착각하지 않게 버전까지 확인)
  if curl -fsS http://127.0.0.1:8000/api/health 2>/dev/null | grep -q "\"version\":\"$AUDITON_VERSION\""; then echo "배포 성공: $AUDITON_VERSION"; echo "$(date -Is) deployed $AUDITON_VERSION" >> var/deploy.log; exit 0; fi
  sleep 3
done
echo "헬스 체크 실패 → $PREV 로 되돌림"
git checkout -q "$PREV"
export AUDITON_VERSION=$(git rev-parse --short HEAD)
sudo -E docker compose --profile "$PROFILE" up -d --build
git checkout -q main
echo "$(date -Is) rollback to $PREV" >> var/deploy.log
exit 1
