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

if [ ! -d "$DIR/.git" ]; then
  # 비공개 저장소: 서버의 SSH 공개키를 저장소 Deploy keys(읽기 전용)에 등록한 뒤 SSH 주소로 받는다
  [ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -q
  ssh-keyscan -q github.com >> ~/.ssh/known_hosts 2>/dev/null
  if ! git clone -q "${REPO_SSH:-git@github.com:ganadidududu/infosys2026-hackaton.git}" "$DIR"; then
    echo; echo "↓ 이 공개키를 GitHub 저장소 Settings → Deploy keys 에 추가(쓰기 권한 끔)한 뒤 다시 실행하세요"
    cat ~/.ssh/id_ed25519.pub; exit 1
  fi
fi
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
# 2분마다 GitHub main을 확인해 스스로 배포(새 커밋이 있을 때만)
sudo tee /etc/systemd/system/auditon-deploy.service >/dev/null <<UNIT
[Unit]
Description=Auditon auto deploy
[Service]
Type=oneshot
User=$USER
WorkingDirectory=$DIR
ExecStart=/bin/bash $DIR/deploy/auto-update.sh
UNIT
sudo tee /etc/systemd/system/auditon-deploy.timer >/dev/null <<UNIT
[Unit]
Description=Auditon auto deploy every 2 min
[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
[Install]
WantedBy=timers.target
UNIT
echo "%sudo ALL=(ALL) NOPASSWD: /usr/bin/docker" | sudo tee /etc/sudoers.d/auditon-docker >/dev/null
sudo systemctl daemon-reload && sudo systemctl enable --now auditon-backup.timer auditon-deploy.timer

echo
echo "다음: $DIR/.env 를 채운 뒤 ($DIR/.deploy-profile 에 tunnel 또는 quick 한 단어)"
echo "  cd $DIR && sudo docker compose --profile tunnel up -d --build   # 도메인 있음"
echo "  cd $DIR && sudo docker compose --profile quick  up -d --build   # 도메인 없음(임시 주소)"
