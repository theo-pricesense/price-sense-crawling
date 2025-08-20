# Price Sense 크롤링 시스템

Price Sense B2B SaaS 서비스의 Python 기반 크롤링 시스템입니다. 한국 주요 이커머스 플랫폼에서 상품 가격 및 재고 정보를 실시간으로 수집하여 PostgreSQL 데이터베이스에 저장합니다.

## 📋 목차

- [지원 플랫폼](#지원-플랫폼)
- [설치 및 설정](#설치-및-설정)
- [환경 변수 설정](#환경-변수-설정)
- [사용법](#사용법)
- [아키텍처](#아키텍처)
- [개발 가이드](#개발-가이드)
- [모니터링](#모니터링)
- [문제 해결](#문제-해결)

## 🛒 지원 플랫폼

현재 지원하는 이커머스 플랫폼:

- **쿠팡** (coupang.com) - Selenium 기반
- **네이버쇼핑** (shopping.naver.com) - HTTP + Selenium 하이브리드
- **스마트스토어** (smartstore.naver.com) - React 앱 전용

## 🔧 설치 및 설정

### 1. 시스템 요구사항

- Python 3.11+
- Chrome/Chromium 브라우저
- Redis 서버
- PostgreSQL 데이터베이스

### 2. 의존성 설치

```bash
# 프로젝트 클론
git clone <repository-url>
cd price-sense-crawling

# Python 의존성 설치
pip install -r requirements.txt
```

### 3. Chrome 드라이버 설치

```bash
# macOS (Homebrew)
brew install chromedriver

# Ubuntu
sudo apt-get update
sudo apt-get install chromium-chromedriver

# 또는 수동 다운로드
# https://chromedriver.chromium.org/
```

## ⚙️ 환경 변수 설정

`.env` 파일을 생성하고 다음 설정을 추가하세요:

```env
# 데이터베이스 연결
DATABASE_URL=postgresql://username:password@localhost:5432/pricesense

# Redis 연결
REDIS_URL=redis://localhost:6379/0

# 크롤러 설정
LOG_LEVEL=INFO
CHROME_DRIVER_PATH=/usr/local/bin/chromedriver

# Redis 큐 이름 (선택사항)
CRAWL_QUEUE_NAME=price_crawl_tasks
RESULT_QUEUE_NAME=price_crawl_results
DEAD_LETTER_QUEUE=price_crawl_failed

# 성능 설정
MAX_RETRIES=3
REQUEST_DELAY=2.0
```

### 환경 변수 설명

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `DATABASE_URL` | ✅ | - | PostgreSQL 연결 URL |
| `REDIS_URL` | ✅ | - | Redis 연결 URL |
| `LOG_LEVEL` | ❌ | INFO | 로그 레벨 (DEBUG/INFO/WARNING/ERROR) |
| `CHROME_DRIVER_PATH` | ❌ | 자동 탐지 | ChromeDriver 실행 파일 경로 |
| `MAX_RETRIES` | ❌ | 3 | 최대 재시도 횟수 |
| `REQUEST_DELAY` | ❌ | 2.0 | 요청 간 기본 지연 시간(초) |

## 🚀 사용법

### 1. 기본 실행

```bash
# 단일 워커 실행
python -m crawlers.worker

# 멀티 워커 실행 (4개 프로세스)
python -m crawlers.worker --workers 4

# 커스텀 워커 ID 설정
python -m crawlers.worker --workers 2 --worker-prefix "prod-worker"
```

### 2. 개별 플랫폼 테스트

개별 크롤러를 테스트하려면:

```bash
# 쿠팡 크롤러 테스트
python -m crawlers.worker --test coupang \
  --url "https://www.coupang.com/vp/products/6339984726" \
  --product-id "test-001"

# 네이버쇼핑 크롤러 테스트
python -m crawlers.worker --test naver_shopping \
  --url "https://shopping.naver.com/catalog/products/12345" \
  --product-id "test-002"

# 스마트스토어 크롤러 테스트
python -m crawlers.worker --test smartstore \
  --url "https://smartstore.naver.com/store/products/12345" \
  --product-id "test-003"
```

### 3. 로그 레벨 조정

```bash
# 디버그 모드
python -m crawlers.worker --log-level DEBUG

# 에러만 출력
python -m crawlers.worker --log-level ERROR --workers 4
```

### 4. Redis 큐에 작업 추가

Python 코드로 크롤링 작업을 큐에 추가:

```python
from storage.redis_client import task_queue

# 작업 데이터
task_data = {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "product_id": "12345",
    "url": "https://www.coupang.com/vp/products/6339984726",
    "platform": "coupang",
    "user_id": "user123"
}

# 큐에 추가 (일반 우선순위)
success = task_queue.push_task(task_data, priority="normal")

# 높은 우선순위로 추가
success = task_queue.push_task(task_data, priority="high")
```

### 5. 큐 상태 확인

```python
from storage.redis_client import task_queue

# 큐 통계 조회
stats = task_queue.get_queue_stats()
print(stats)
# 출력: {'crawl_high': 5, 'crawl_normal': 23, 'result': 1, 'dead_letter': 0}
```

## 🏗️ 아키텍처

### 시스템 구성요소

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   NestJS API    │    │  Redis Queues   │    │ Python Crawler  │
│     Server      │───▶│                 │───▶│     Workers     │
│                 │    │ • Tasks         │    │                 │
│ • 스케줄링       │    │ • Results       │    │ • 크롤링 실행    │
│ • API 제공      │    │ • Failed        │    │ • 데이터 검증    │
│ • 알림 발송     │    │                 │    │ • DB 저장       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                        │
                                │      ┌─────────────────┐
                                └─────▶│   PostgreSQL    │
                                       │    Database     │
                                       │                 │
                                       │ • 상품 정보      │
                                       │ • 가격/재고 이력 │
                                       │ • 크롤링 로그    │
                                       └─────────────────┘
```

### 워커 프로세스 흐름

```
Redis 큐 ──┐
          ├─▶ Queue Handler ──▶ Platform Crawler ──▶ Data Validator ──▶ Database
          │                                                             │
          │                  ┌─ Anti-Detection ◀───────────────────────┘
          │                  │
          └──────────────────▶ Results Queue
```

### 데이터 플로우

1. **NestJS 서버**가 크롤링 작업을 Redis 큐에 추가
2. **Python 워커**가 큐에서 작업을 가져옴
3. **플랫폼별 크롤러**가 웹사이트에서 데이터 추출
4. **데이터 검증**으로 품질 확인
5. **PostgreSQL**에 가격/재고 이력 저장
6. **결과**를 Redis 결과 큐로 전송

## 🛠️ 개발 가이드

### 새로운 플랫폼 추가

1. `crawlers/platforms/` 디렉토리에 새 크롤러 파일 생성
2. `BaseCrawler` 클래스 상속
3. 필수 메서드 구현:

```python
from crawlers.core.base_crawler import BaseCrawler, CrawlResult
from models.base import PlatformType

class NewPlatformCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        super().__init__(platform=PlatformType.NEW_PLATFORM, **kwargs)
    
    def _is_platform_url(self, url: str) -> bool:
        # URL 검증 로직
        return 'newplatform.com' in url.lower()
    
    def get_platform_selectors(self) -> Dict[str, str]:
        # CSS 셀렉터 정의
        return {
            'product_name': ['.product-title'],
            'current_price': ['.price'],
            # ...
        }
    
    async def extract_product_data(self, product_id: str, url: str) -> CrawlResult:
        # 실제 크롤링 로직
        pass
```

4. `queue_handler.py`에 새 크롤러 등록:

```python
self.crawler_classes[PlatformType.NEW_PLATFORM] = NewPlatformCrawler
```

### 커스텀 검증 규칙 추가

`utils/validation.py`에서 검증 규칙을 수정하거나 추가:

```python
class CustomValidator:
    def validate_custom_field(self, value: Any) -> ValidationResult:
        result = ValidationResult(True, 1.0, [], [])
        
        # 커스텀 검증 로직
        if not self.is_valid_value(value):
            result.add_error("Custom validation failed")
            result.score = 0.0
        
        return result
```

### 설정 변경

`config/settings.py`에서 시스템 설정을 조정할 수 있습니다:

```python
class CrawlerSettings(BaseSettings):
    max_retries: int = 3
    request_delay: float = 2.0
    timeout: int = 30
    
    # 플랫폼별 지연시간 커스터마이징
    platform_delays: Dict[str, float] = {
        "coupang": 3.0,
        "naver_shopping": 2.0,
        # ...
    }
```

## 📊 모니터링

### 로그 확인

```bash
# 실시간 로그 확인
tail -f logs/crawler.log

# 에러 로그만 확인
grep "ERROR" logs/crawler.log

# 특정 플랫폼 로그 필터링
grep "coupang" logs/crawler.log
```

### Redis 큐 모니터링

```python
from storage.redis_client import task_queue

# 주기적으로 큐 상태 확인
import time
while True:
    stats = task_queue.get_queue_stats()
    print(f"Queue status: {stats}")
    time.sleep(60)
```

### 성능 메트릭

워커 실행 중 성능 통계가 자동으로 출력됩니다:

```
=== Final Statistics ===
Runtime: 3600.0 seconds
Total tasks processed: 1250
Successful tasks: 1187
Failed tasks: 63
Success rate: 95.0%
Average time per task: 2.9 seconds
```

## 🔧 문제 해결

### 일반적인 문제들

#### 1. ChromeDriver 오류

```
selenium.common.exceptions.WebDriverException: 'chromedriver' executable needs to be in PATH
```

**해결방법:**
```bash
# ChromeDriver 설치 확인
chromedriver --version

# PATH에 추가하거나 환경변수 설정
export CHROME_DRIVER_PATH=/usr/local/bin/chromedriver
```

#### 2. Redis 연결 실패

```
redis.exceptions.ConnectionError: Error 61 connecting to localhost:6379. Connection refused.
```

**해결방법:**
```bash
# Redis 서버 시작
redis-server

# 또는 Docker로 실행
docker run -d -p 6379:6379 redis:alpine
```

#### 3. 데이터베이스 연결 오류

```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) could not connect to server
```

**해결방법:**
```bash
# PostgreSQL 서버 상태 확인
pg_ctl status

# 연결 URL 확인
echo $DATABASE_URL
```

#### 4. 메모리 부족

워커가 메모리 부족으로 종료되는 경우:

```bash
# 워커 수 줄이기
python -m crawlers.worker --workers 2

# 또는 시스템 메모리 증설
```

### 디버깅 모드

상세한 디버깅을 위해:

```bash
# 디버그 로그 + headless 비활성화 (브라우저 창 표시)
python -m crawlers.worker --test coupang --url "..." --log-level DEBUG
```

### 큐 초기화

개발 중 큐를 초기화하려면:

```python
from storage.redis_client import task_queue

# 모든 큐 초기화
task_queue.clear_queue("all")

# 특정 큐만 초기화
task_queue.clear_queue("crawl")  # 크롤링 큐
task_queue.clear_queue("result")  # 결과 큐
task_queue.clear_queue("dead_letter")  # 실패 큐
```

## 📞 지원

문제가 발생하면 다음을 확인해주세요:

1. **로그 파일**: 에러 메시지와 스택 트레이스 확인
2. **환경 변수**: 모든 필수 설정이 올바른지 확인
3. **의존성**: Redis, PostgreSQL, Chrome이 실행 중인지 확인
4. **리소스**: 메모리, CPU, 디스크 사용량 확인

## 📝 라이선스

이 프로젝트는 Price Sense 전용 크롤링 시스템입니다.

---

**Price Sense 크롤링 시스템** - 한국 이커머스 가격 모니터링의 새로운 표준 🚀