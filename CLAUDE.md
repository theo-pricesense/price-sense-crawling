# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Price Sense B2B SaaS 서비스의 Python 크롤링 시스템입니다. 한국 주요 이커머스 플랫폼의 상품 가격 및 재고 정보를 수집합니다.

자세한 기획 내용은 `PRD_CRAWLER.md` 파일을 참조하세요.

## Development Setup

### Prerequisites
- Python 3.11+
- Redis (작업 큐용)
- PostgreSQL (데이터 저장용)
- Chrome/Chromium (Selenium용)

### Environment Variables
```bash
# .env 파일 설정
DATABASE_URL=postgresql://username:password@localhost:5432/pricesense
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
CHROME_DRIVER_PATH=/usr/local/bin/chromedriver
```

### Common Commands
```bash
# 의존성 설치
pip install -r requirements.txt

# 크롤링 워커 시작
python -m crawlers.worker

# 특정 플랫폼 크롤러 테스트
python -m crawlers.platforms.coupang --test-url "https://..."

# 테스트 실행
pytest tests/

# 코드 포맷팅
black .
flake8 .

# 타입 체킹
mypy .
```

## Project Architecture

### Directory Structure
```
crawlers/
├── platforms/          # 플랫폼별 크롤링 모듈
│   ├── coupang.py      # 쿠팡 크롤러
│   ├── naver.py        # 네이버쇼핑 크롤러
│   ├── elevenst.py     # 11번가 크롤러
│   └── smartstore.py   # 스마트스토어 크롤러
├── core/               # 핵심 공통 기능
│   ├── base_crawler.py # 기본 크롤러 클래스
│   ├── queue_handler.py # Redis 큐 처리
│   └── data_extractor.py # 데이터 추출 유틸리티
models/                 # 데이터베이스 모델
├── product.py
├── price_history.py
└── stock_history.py
storage/                # 데이터베이스 연결
├── connection.py
└── repositories/
utils/                  # 유틸리티 함수
├── anti_detection.py   # 안티 디텍션 기능
├── retry.py           # 재시도 로직
└── validation.py      # 데이터 검증
config/                # 설정 파일
└── settings.py
tests/                 # 테스트 코드
```

## Technology Stack

- **Web Scraping**: Selenium, Playwright (JavaScript 렌더링)
- **HTML Parsing**: BeautifulSoup4
- **HTTP Requests**: httpx (async 지원)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Task Queue**: Redis (작업 수신)
- **Anti-Detection**: Fake User-Agent, IP 로테이션
- **Configuration**: Pydantic Settings

## Development Guidelines

### 새로운 플랫폼 크롤러 추가 시
1. `crawlers/platforms/` 에 새 파일 생성
2. `BaseCrawler` 클래스 상속  
3. `extract_product_data()` 메서드 구현
4. 플랫폼별 셀렉터 및 파싱 로직 작성
5. 테스트 케이스 추가

### 코딩 컨벤션
- 타입 힌트 필수 사용
- docstring 작성 (Google style)
- 에러 처리 및 로깅 필수
- 설정값은 환경변수로 관리
- 크롤링 지연시간 준수 (플랫폼별 1-5초)
- 신뢰도 점수 0.7 이상만 DB 저장

### 테스트 작성 규칙
- 각 플랫폼별 크롤러 단위 테스트 필수
- Mock 데이터 활용으로 실제 사이트 요청 방지  
- 데이터 검증 로직 테스트 포함
- 에러 케이스 테스트 작성

### 보안 및 컴플라이언스
- robots.txt 준수 필수
- 요청 간격 1-5초 유지
- User-Agent 로테이션 적용
- 사이트 이용약관 준수
- 개인정보 수집 금지