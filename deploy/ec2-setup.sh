#!/usr/bin/env bash
# EC2(Ubuntu 24.04)에서 한 번 실행: 도커 설치 → 코드 받기 → 백업 타이머 등록.
# 사용: curl -fsSL <이 파일 raw 주소> | bash   또는 저장소를 받은 뒤 bash deploy/ec2-setup.sh
set -euo pipefail
REPO=${REPO:-https://github.com/ganadidududu/infosys2026-hackaton.git}
DIR=${DIR:-$HOME/auditon}

sudo apt-get update -y
sudo apt-get install -y ca-certificates curl git unzip
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
if ! command -v aws >/dev/null; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscli.zip
  unzip -q /tmp/awscli.zip -d /tmp && sudo /tmp/aws/install
fi

[ -d "$DIR/.git" ] || git clone "$REPO" "$DIR"
cd "$DIR"
[ -f .env ] || cp .env.example .env
mkdir -p var && sudo chown 1000:1000 var

# 10분마다 S3 백업 (S3_BUCKET이 비어 있으면 건너뜀)
sudo tee /etc/systemd/system/auditon-backup.service >/dev/null <<UNIT
[Unit]
Description=Auditon S3 backup
[Service]
Type=oneshot
WorkingDirectory=$DIR
ExecStart=/bin/bash $DIR/deploy/backup.sh
UNIT
sudo tee /etc/systemd/system/auditon-backup.timer >/dev/null <<UNIT
[Unit]
Description=Auditon S3 backup every 10 min
[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
UNIT
sudo systemctl daemon-reload && sudo systemctl enable --now auditon-backup.timer

echo
echo "다음: $DIR/.env 를 채운 뒤"
echo "  cd $DIR && sudo docker compose --profile tunnel up -d --build   # 도메인 있음"
echo "  cd $DIR && sudo docker compose --profile quick  up -d --build   # 도메인 없음(임시 주소)"
