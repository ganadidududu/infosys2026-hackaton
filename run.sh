#!/usr/bin/env bash
# Auditon 한 번에 실행: 프론트엔드를 빌드하고 백엔드(8000)가 화면까지 함께 띄운다.
set -e
cd "$(dirname "$0")"
# .env가 있으면 읽는다(OPENROUTER_API_KEY, AUDITON_LLM=live 등)
set -a; [ -f .env ] && . ./.env; set +a
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install -q --disable-pip-version-check -r backend/requirements.txt
if command -v npm >/dev/null 2>&1; then
  [ -d frontend/node_modules ] || (cd frontend && npm install)
  (cd frontend && npm run build)
elif [ -d frontend/dist ]; then
  echo "Node.js가 없어 미리 빌드된 화면(frontend/dist)을 사용합니다."
else
  echo "Node.js(npm)가 필요합니다: https://nodejs.org" && exit 1
fi
[ -f data/synthetic/tune/dataset.json ] || backend/.venv/bin/python data/synthetic/generate.py --set tune
echo ""
echo "  ▶ http://localhost:8000          학생 공개 페이지"
echo "  ▶ http://localhost:8000/admin    관리자(집행부·감사위원회)"
echo ""
cd backend && exec .venv/bin/uvicorn app.main:app --port 8000
