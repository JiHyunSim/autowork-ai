# n8n 인프라 설정 가이드

## 개요

AutoWork AI 콘텐츠 자동화 파이프라인(CMP)을 위한 n8n 서버 설정입니다.

## 빠른 시작

### 1. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열고 실제 값으로 변경
```

### 2. n8n 서버 실행

```bash
docker compose up -d
```

### 3. n8n 접속

- URL: http://localhost:5678
- 초기 계정: .env의 N8N_BASIC_AUTH_USER / N8N_BASIC_AUTH_PASSWORD

## API Credentials 설정

n8n 접속 후 **Settings > Credentials** 에서 아래 항목을 추가합니다:

### Claude API (Anthropic)
- Type: HTTP Request (Header Auth)
- Name: `Claude API`
- Header Name: `x-api-key`
- Header Value: `{ANTHROPIC_API_KEY}`

### YouTube Data API
- Type: Google OAuth2 API
- Scopes: `https://www.googleapis.com/auth/youtube.upload`

### 티스토리 API
- Type: HTTP Request (OAuth2)
- Authorization URL: `https://www.tistory.com/oauth/authorize`
- Access Token URL: `https://www.tistory.com/oauth/access_token`

### Instagram Graph API
- Type: HTTP Request (OAuth2)
- Access Token: Instagram Business 계정 장기 액세스 토큰

### 쿠팡 파트너스 API
- Type: HTTP Request (Header Auth)
- HMAC 서명 방식 (connectors/coupang.py 참고)

## 디렉토리 구조

```
infrastructure/n8n/
├── docker-compose.yml      # Docker 설정
├── .env.example            # 환경변수 템플릿
├── README.md               # 이 파일
├── custom-hooks/
│   └── hooks.js            # 워크플로우 이벤트 훅
├── workflows/              # n8n 워크플로우 JSON 파일 (자동 임포트)
└── init-scripts/           # PostgreSQL 초기화 SQL
```

## 모니터링

워크플로우 실행 로그:
```bash
docker logs autowork-n8n -f
```

PostgreSQL 연결:
```bash
docker exec -it autowork-n8n-postgres psql -U n8n -d n8n
```
