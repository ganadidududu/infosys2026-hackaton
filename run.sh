#!/usr/bin/env bash
# Auditon 한 번에 실행: 프론트엔드를 빌드하고 백엔드(8000)가 화면까지 함께 띄운다.
set -e
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then (cd frontend && npm install); fi
(cd frontend && npm run build)
[ -f data/synthetic/tune/dataset.json ] || backend/.venv/bin/python data/synthetic/generate.py --set tune
echo ""
echo "  ▶ http://localhost:8000          학생 공개 페이지"
echo "  ▶ http://localhost:8000/admin    관리자(집행부·감사위원회)"
echo ""
cd backend && exec .venv/bin/uvicorn app.main:app --port 8000
