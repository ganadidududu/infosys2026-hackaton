# Auditon 배포 (Cloudflare + AWS EC2)

```
브라우저 ──HTTPS──▶ Cloudflare (Pages: 화면 / Tunnel·WAF: API)
                         │  (EC2는 포트를 밖으로 열지 않음)
                         ▼
                AWS EC2 · Docker ─ api(FastAPI·OCR·대사·채점) ─▶ EBS(var/: 상태·업로드)
                         │                                  └─▶ S3(10분마다 암호화 백업)
                         └─▶ 외부 LLM API (가명처리 텍스트만)
```

## 안정성 장치
| 장치 | 위치 |
| --- | --- |
| 헬스 체크 `/api/health` (저장소 쓰기·데이터·기준안 확인) | `backend/app/main.py`, Docker `HEALTHCHECK` |
| 컨테이너 자동 재시작 `restart: unless-stopped` | `docker-compose.yml` |
| 상태 원자 저장(임시 파일 → rename) | `save_state` |
| 요청 로그 한 줄 JSON(본문 미기록) + 로그 회전 10MB×5 | `access_log`, compose `logging` |
| LLM 실패 시 2회 재시도 후 전 조항 "확인 필요"(점수를 지어내지 않음) | `backend/audit/llm.py` |
| 숫자(대사·감점·경고)는 결정적 코드 | `reconcile/`, `audit/engine.py` |
| 배포 후 헬스 체크 실패 시 이전 버전으로 자동 되돌림 | `deploy/update.sh` |
| 푸시마다 테스트·빌드·이미지 헬스 체크 | `.github/workflows/ci.yml` |
| S3 백업(SSE) 10분 + 하루 스냅숏 | `deploy/backup.sh`, systemd timer |
| CORS를 화면 주소로만 제한 | `AUDITON_CORS` |

## 1. AWS
1. EC2 만들기: **Ubuntu 24.04, t3.medium 이상(OCR), 디스크 30GB**, 서울(ap-northeast-2).
2. 보안 그룹: **인바운드는 SSH(22) 내 IP만.** 80/443은 열지 않는다(Tunnel이 바깥으로 나가며 연결).
3. S3 버킷 하나(퍼블릭 차단 유지) + EC2에 그 버킷 쓰기 권한 IAM 역할 연결.
4. SSH 접속 후:
   ```bash
   git clone https://github.com/ganadidududu/infosys2026-hackaton.git ~/auditon
   bash ~/auditon/deploy/ec2-setup.sh
   nano ~/auditon/.env      # 키·S3_BUCKET·AUDITON_CORS 채우기
   ```
   비공개 저장소라 clone 때 GitHub 토큰(또는 deploy key)이 필요하다.

## 2. Cloudflare
- **도메인 있음:** Zero Trust → Networks → Tunnels → 터널 생성 → 토큰을 `.env`의 `CLOUDFLARE_TUNNEL_TOKEN`에.
  Public hostname `api.<도메인>` → `http://api:8000`.
  ```bash
  cd ~/auditon && sudo docker compose --profile tunnel up -d --build
  ```
- **도메인 없음(임시):** `sudo docker compose --profile quick up -d --build` 후
  `sudo docker compose logs quick-tunnel | grep trycloudflare` 로 주소 확인(재시작하면 바뀜).

### 화면(Pages)
Workers & Pages → Pages → GitHub 연결 → 이 저장소
- Root directory `frontend`, Build `npm run build`, Output `dist`
- 환경 변수 `VITE_API_BASE=https://api.<도메인>`
- `.env`의 `AUDITON_CORS`에 Pages 주소 추가

(Pages 없이 터널 주소 하나로 화면+API를 함께 써도 된다. 컨테이너가 화면도 띄운다.)

## 3. 업데이트
```bash
cd ~/auditon && PROFILE=tunnel bash deploy/update.sh
```

## 로컬에서 그대로 돌려 보기
```bash
cp .env.example .env
docker compose up -d --build      # http://localhost:8000
```
