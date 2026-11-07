#!/usr/bin/env bash
# 상태 JSON·업로드 파일을 S3로 백업(서버 측 암호화). EC2에 S3 쓰기 권한이 있는 IAM 역할을 붙여 둔다.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
[ -n "${S3_BUCKET:-}" ] || { echo "S3_BUCKET 없음: 백업 건너뜀"; exit 0; }
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
aws s3 sync var/ "s3://$S3_BUCKET/live/" --sse AES256 --region "${AWS_REGION:-ap-northeast-2}" --delete --only-show-errors
# 하루 한 번 스냅숏(복구 지점)
if [ "$(date -u +%H%M | cut -c1-3)" = "000" ]; then
  tar -czf "/tmp/auditon-$STAMP.tgz" -C var .
  aws s3 cp "/tmp/auditon-$STAMP.tgz" "s3://$S3_BUCKET/snapshots/" --sse AES256 --region "${AWS_REGION:-ap-northeast-2}" --only-show-errors
  rm -f "/tmp/auditon-$STAMP.tgz"
fi
echo "backup ok $STAMP"
