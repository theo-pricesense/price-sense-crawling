# Price Sense 크롤러 시스템 PRD

## 1. 개요

### 1.1 목적
Price Sense B2B SaaS 서비스의 핵심 구성요소인 Python 기반 크롤링 시스템을 구현합니다. 한국 주요 이커머스 플랫폼에서 상품 가격 및 재고 정보를 실시간으로 수집하여 PostgreSQL 데이터베이스에 저장하는 역할을 담당합니다.

### 1.2 시스템 역할
분리된 아키텍처에서 크롤러의 역할:
- **NestJS 서버**: 스케줄 관리, API 제공, 변화 감지, 알림 발송
- **Python 크롤러** (이 시스템): 웹사이트 스크래핑, 데이터 수집 및 DB 저장
- **Redis Queue**: 두 시스템 간 작업 큐 역할
- **PostgreSQL**: 공유 데이터베이스

## 2. 핵심 기능 요구사항

### 2.1 크롤링 작업 처리
- Redis 큐에서 크롤링 작업 수신 및 처리
- 작업 우선순위 기반 처리 (normal/high)
- 실패 시 자동 재시도 로직 (최대 3회)
- 작업 완료 상태를 Redis로 응답

### 2.2 플랫폼별 데이터 수집

#### 1차 지원 플랫폼
1. **쿠팡** (coupang.com)
2. **네이버쇼핑** (shopping.naver.com)
3. **스마트스토어** (smartstore.naver.com)
4. **11번가** (11st.co.kr)

#### 수집 데이터
- **기본 정보**: 상품명, 현재 가격, 재고 상태
- **옵션 정보**: 옵션별 가격/재고 (색상, 사이즈 등)
- **프로모션**: 할인율, 쿠폰 정보, 특가 여부
- **이미지**: 대표 상품 이미지 URL
- **메타데이터**: 카테고리, 브랜드, 평점 (가능한 경우)

### 2.3 데이터 품질 관리
- **신뢰도 점수**: 데이터 추출 정확도를 0-1 스케일로 측정
- **데이터 검증**: 가격/재고 데이터 유효성 검사
- **중복 방지**: 10분 이내 동일 상품 중복 수집 방지
- **오류 처리**: 네트워크/파싱 오류 시 상세 로깅

## 3. 기술 요구사항

### 3.1 웹 스크래핑 기술
- **Selenium**: JavaScript 렌더링이 필요한 사이트
- **Playwright**: 고성능 브라우저 자동화 (향후 마이그레이션)
- **BeautifulSoup4**: HTML 파싱
- **httpx**: 비동기 HTTP 요청 (정적 페이지)

### 3.2 안티 디텍션 전략
- **User-Agent 로테이션**: 실제 브라우저 UA 풀 사용
- **요청 지연**: 플랫폼별 적절한 지연 시간 (1-5초)
- **세션 관리**: 쿠키 및 세션 상태 유지
- **Headless 모드**: 브라우저 감지 회피
- **robots.txt 준수**: 각 사이트 크롤링 정책 확인

### 3.3 성능 요구사항
- **병렬 처리**: 멀티프로세싱으로 동시 크롤링 (최대 10개 프로세스)
- **메모리 사용량**: 프로세스당 최대 1GB
- **처리 속도**: 상품당 평균 10초 이내 처리
- **가동률**: 99% 이상 (24/7 운영)

## 4. 데이터베이스 연동

### 4.1 직접 저장 테이블

#### price_history
```sql
CREATE TABLE price_history (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    price DECIMAL(12,2) NOT NULL,
    discount_rate DECIMAL(5,2),
    promotion_info TEXT,
    confidence_score DECIMAL(3,2) NOT NULL,
    recorded_at TIMESTAMP DEFAULT NOW()
);
```

#### stock_history
```sql
CREATE TABLE stock_history (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    stock_status VARCHAR(20) NOT NULL, -- available/out_of_stock/limited
    stock_quantity INTEGER,
    confidence_score DECIMAL(3,2) NOT NULL,
    recorded_at TIMESTAMP DEFAULT NOW()
);
```

#### crawl_logs
```sql
CREATE TABLE crawl_logs (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    platform VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL, -- success/failed/partial
    error_message TEXT,
    execution_time INTEGER, -- 밀리초
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 배치 처리
- 수집된 데이터를 배치 단위로 DB 삽입 (100개씩)
- 트랜잭션 기반 원자적 처리
- 연결 풀링으로 DB 부하 최적화

## 5. Redis 큐 프로토콜

### 5.1 작업 요청 메시지
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "product_id": 123,
    "url": "https://www.coupang.com/vp/products/6339984726",
    "platform": "coupang",
    "priority": "normal",
    "retry_count": 0,
    "user_id": 456,
    "created_at": "2024-01-01T00:00:00Z"
}
```

### 5.2 작업 완료 응답
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "success",
    "data": {
        "price": 29900,
        "discount_rate": 15.5,
        "stock_status": "available",
        "stock_quantity": null,
        "promotion_info": "로켓배송, 15% 할인쿠폰",
        "confidence_score": 0.95,
        "image_url": "https://image.coupangcdn.com/..."
    },
    "execution_time": 8500,
    "completed_at": "2024-01-01T00:01:30Z"
}
```

### 5.3 실패 응답
```json
{
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "failed",
    "error": "상품 페이지를 찾을 수 없습니다",
    "error_code": "PRODUCT_NOT_FOUND",
    "retry_count": 2,
    "completed_at": "2024-01-01T00:01:30Z"
}
```

## 6. 플랫폼별 크롤링 전략

### 6.1 쿠팡 (coupang.com)
- **접근 방식**: Selenium (JavaScript 필수)
- **주요 셀렉터**: 
  - 가격: `.total-price .price`
  - 재고: `.out-of-stock, .available`
  - 상품명: `.prod-buy-header__title`
- **특이사항**: 
  - 로그인 없이 접근 가능
  - 로켓배송 여부 확인
  - 옵션별 가격 차이 존재

### 6.2 네이버쇼핑 (shopping.naver.com)
- **접근 방식**: httpx + BeautifulSoup (정적 파싱 가능)
- **주요 셀렉터**:
  - 가격: `.price_num`
  - 재고: `.product_info_area .stock`
  - 상품명: `.product_title`
- **특이사항**:
  - API 형태 응답 제공
  - 여러 판매자 가격 존재

### 6.3 스마트스토어 (smartstore.naver.com)
- **접근 방식**: Selenium (React 기반)
- **주요 셀렉터**:
  - 가격: `.price .num`
  - 재고: `.buy_area .quantity`
  - 상품명: `.product_name`
- **특이사항**:
  - 네이버 계정 연동
  - 옵션 선택 시 동적 가격 변경

### 6.4 11번가 (11st.co.kr)
- **접근 방식**: Selenium
- **주요 셀렉터**:
  - 가격: `.sale_price`
  - 재고: `.stock_status`
  - 상품명: `.pname`
- **특이사항**:
  - 글로벌/일반상품 구분
  - 쿠폰 적용 가격 별도 표시

## 7. 모니터링 및 로깅

### 7.1 성능 지표
- **처리 성공률**: 95% 이상 유지
- **평균 처리 시간**: 상품당 10초 이내
- **동시 처리 용량**: 100개 상품/분
- **에러율**: 5% 이하

### 7.2 로깅 시스템
- **구조화된 로깅**: JSON 형태 로그
- **로그 레벨**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **필수 로그 항목**:
  - 작업 시작/완료 시간
  - 추출된 데이터 및 신뢰도
  - 에러 발생 시 상세 정보
  - 성능 메트릭 (응답시간, 메모리 사용량)

### 7.3 알림 시스템
- **Sentry**: 에러 추적 및 알림
- **CloudWatch**: AWS 인프라 모니터링
- **Slack**: 중요 이벤트 실시간 알림

## 8. 보안 및 컴플라이언스

### 8.1 데이터 보안
- **환경 변수**: 민감 정보는 환경 변수로 관리
- **연결 암호화**: PostgreSQL SSL 연결 필수
- **Redis 인증**: AUTH 및 TLS 적용

### 8.2 크롤링 윤리
- **robots.txt 준수**: 모든 대상 사이트의 정책 확인
- **요청 제한**: 과도한 트래픽 방지 (초당 최대 1요청)
- **사용자 약관 준수**: 각 플랫폼의 이용약관 검토
- **개인정보 미수집**: 상품 정보만 수집, 개인정보 제외

## 9. 개발 및 배포

### 9.1 개발 환경
- **Python 3.11+**
- **Docker**: 로컬 개발 환경 표준화
- **Poetry**: 의존성 관리
- **pytest**: 테스트 프레임워크

### 9.2 CI/CD
- **GitHub Actions**: 자동 테스트 및 배포
- **AWS ECS**: 컨테이너 기반 배포
- **Blue-Green 배포**: 무중단 배포
- **Auto Scaling**: 트래픽에 따른 자동 확장

### 9.3 환경별 설정
- **Development**: 로컬 PostgreSQL, Redis
- **Staging**: AWS RDS, ElastiCache
- **Production**: Multi-AZ RDS, Redis Cluster

## 10. 향후 확장 계획

### 10.1 추가 플랫폼 (Phase 2)
- G마켓 (gmarket.co.kr)
- SSG (ssg.com)
- 위메프 (wemakeprice.com)
- 옥션 (auction.co.kr)

### 10.2 기능 확장
- **API 기반 크롤링**: 공식 API 활용으로 안정성 개선
- **AI 기반 데이터 검증**: 이상치 탐지 및 자동 수정
- **실시간 스트리밍**: WebSocket 기반 실시간 가격 변동 추적
- **글로벌 확장**: 해외 이커머스 플랫폼 지원

### 10.3 성능 최적화
- **캐싱 레이어**: Redis 기반 결과 캐싱
- **CDN 활용**: 이미지 및 정적 자원 캐싱
- **Database 샤딩**: 대용량 데이터 처리를 위한 분산 저장
- **ML 기반 최적화**: 크롤링 패턴 학습으로 효율성 개선