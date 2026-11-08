#!/usr/bin/env bash
# EC2가 스스로 배포: GitHub main에 새 커밋이 있으면 받아서 다시 빌드 → 헬스 체크 → 실패 시 이전 버전으로 되돌림.
# 서버로 들어오는 포트를 열 필요가 없다(서버가 GitHub로 나가서 가져옴). systemd 타이머가 2분마다 실행.
set -euo pipefail
cd "$(dirname "$0")/.."
exec 9>/tmp/auditon-deploy.lock
flock -n 9 || { echo "이미 배포 중"; exit 0; }
git fetch -q origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0
echo "새 커밋 ${LOCAL:0:7} → ${REMOTE:0:7}"
PROFILE=$(cat .deploy-profile 2>/dev/null || echo tunnel) bash deploy/update.sh
