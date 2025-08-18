# 데이터베이스 연동 가이드

## 개요

Price Sense 크롤러 시스템은 NestJS API 서버와 PostgreSQL 데이터베이스를 공유합니다. 크롤러는 주로 상품 데이터를 읽고, 가격/재고 이력을 저장하는 역할을 담당합니다.

## 데이터베이스 아키텍처

### 공유 데이터베이스 구조
```
PostgreSQL Database (pricesense)
├── API 서버 관리 테이블
│   ├── users (사용자 정보)
│   ├── subscriptions (구독 정보)
│   └── notifications (알림 설정)
│
└── 크롤러 관련 테이블
    ├── products (상품 기본 정보) - 읽기
    ├── product_categories (카테고리) - 읽기
    ├── product_groups (그룹) - 읽기
    ├── price_history (가격 이력) - 쓰기
    ├── stock_history (재고 이력) - 쓰기
    └── product_scrape_logs (크롤링 로그) - 쓰기
```

## 크롤러 역할별 테이블 접근

### 읽기 전용 테이블

#### 1. products
크롤링 대상 상품 정보 조회
```python
from models.product import Product

# 크롤링 대상 상품 조회
active_products = session.query(Product).filter(
    Product.status == ProductStatus.ACTIVE,
    Product.tracking_enabled == True
).all()
```

#### 2. product_categories
상품 카테고리 정보 참조
```python
from models.product import ProductCategory

# 카테고리 정보 조회
category = session.query(ProductCategory).filter(
    ProductCategory.id == product.category_id
).first()
```

### 쓰기 전용 테이블

#### 1. price_history
가격 변동 데이터 저장
```python
from models.price_history import PriceHistory

# 가격 데이터 저장
price_record = PriceHistory(
    product_id=product.id,
    price=Decimal('29900.00'),
    discount_rate=Decimal('15.50'),
    promotion_info="로켓배송, 15% 할인쿠폰",
    confidence_score=Decimal('0.95'),
    recorded_at=datetime.utcnow()
)
session.add(price_record)
session.commit()
```

#### 2. stock_history
재고 변동 데이터 저장
```python
from models.stock_history import StockHistory

# 재고 데이터 저장
stock_record = StockHistory(
    product_id=product.id,
    stock_status=StockStatus.AVAILABLE,
    stock_quantity=None,  # 정확한 수량 미제공시
    confidence_score=Decimal('0.90'),
    recorded_at=datetime.utcnow()
)
session.add(stock_record)
session.commit()
```

#### 3. product_scrape_logs
크롤링 실행 로그 저장
```python
from models.scrape_logs import ProductScrapeLog

# 성공 로그
success_log = ProductScrapeLog(
    product_id=product.id,
    status="success",
    scraped_data={
        "price": 29900,
        "stock_status": "available",
        "confidence_score": 0.95
    },
    response_time_ms=8500,
    created_at=datetime.utcnow()
)

# 실패 로그
failure_log = ProductScrapeLog(
    product_id=product.id,
    status="failed",
    error_message="상품 페이지를 찾을 수 없습니다",
    response_time_ms=5000,
    created_at=datetime.utcnow()
)
```

## 데이터베이스 연결 설정

### 환경 변수 설정
```bash
# .env 파일
DATABASE_URL=postgresql://username:password@localhost:5432/pricesense
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600
```

### SQLAlchemy 설정
```python
# storage/connection.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from config.settings import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    echo=settings.debug
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db_session():
    """데이터베이스 세션 생성"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

## 데이터 타입 및 제약사항

### 1. 가격 데이터
- **타입**: DECIMAL(12,2)
- **범위**: 최대 99억 9999만 99원까지 지원
- **정밀도**: 소수점 둘째 자리까지

### 2. 신뢰도 점수
- **타입**: DECIMAL(3,2) 
- **범위**: 0.00 ~ 1.00
- **최소 저장 기준**: 0.70 이상

### 3. 재고 상태
```python
class StockStatus(str, Enum):
    AVAILABLE = "available"      # 구매 가능
    LIMITED = "limited"          # 수량 제한
    CRITICAL = "critical"        # 품절 임박
    OUT_OF_STOCK = "out_of_stock"  # 품절
    PREORDER = "preorder"        # 예약 주문
    UNKNOWN = "unknown"          # 확인 불가
```

### 4. 플랫폼 타입
```python
class PlatformType(str, Enum):
    COUPANG = "coupang"
    NAVER_SHOPPING = "naver_shopping"
    ELEVEN_ST = "eleven_st"
    SMART_STORE = "smart_store"
    GMARKET = "gmarket"
    SSG = "ssg"
    WEMAKEPRICE = "wemakeprice"
    TMON = "tmon"
```

## 배치 처리 가이드

### 대량 데이터 삽입
```python
def bulk_insert_price_history(price_records: List[PriceHistory]):
    """가격 이력 대량 삽입"""
    session = SessionLocal()
    try:
        # 배치 단위로 삽입 (100개씩)
        batch_size = 100
        for i in range(0, len(price_records), batch_size):
            batch = price_records[i:i + batch_size]
            session.bulk_save_objects(batch)
            session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
```

### 트랜잭션 관리
```python
def save_crawl_result(product_id: str, price_data: dict, stock_data: dict):
    """크롤링 결과 저장 (트랜잭션)"""
    session = SessionLocal()
    try:
        session.begin()
        
        # 가격 이력 저장
        price_record = PriceHistory(**price_data)
        session.add(price_record)
        
        # 재고 이력 저장
        stock_record = StockHistory(**stock_data)
        session.add(stock_record)
        
        # 성공 로그 저장
        log_record = ProductScrapeLog(
            product_id=product_id,
            status="success",
            scraped_data={**price_data, **stock_data}
        )
        session.add(log_record)
        
        session.commit()
        
    except Exception as e:
        session.rollback()
        
        # 실패 로그 저장
        error_log = ProductScrapeLog(
            product_id=product_id,
            status="failed",
            error_message=str(e)
        )
        session.add(error_log)
        session.commit()
        raise
    finally:
        session.close()
```

## 성능 최적화

### 1. 인덱스 활용
```sql
-- 자주 사용되는 쿼리 패턴에 맞는 인덱스
CREATE INDEX idx_products_tracking ON products(status, tracking_enabled);
CREATE INDEX idx_price_history_recent ON price_history(product_id, recorded_at DESC);
CREATE INDEX idx_stock_history_recent ON stock_history(product_id, recorded_at DESC);
```

### 2. 쿼리 최적화
```python
# 필요한 컬럼만 조회
products = session.query(
    Product.id,
    Product.url,
    Product.platform,
    Product.platform_product_id
).filter(
    Product.status == ProductStatus.ACTIVE,
    Product.tracking_enabled == True
).all()

# 조인을 통한 효율적 데이터 조회
from sqlalchemy.orm import joinedload

products_with_category = session.query(Product)\
    .options(joinedload(Product.category))\
    .filter(Product.status == ProductStatus.ACTIVE)\
    .all()
```

### 3. 연결 풀 관리
```python
# 연결 풀 모니터링
def check_pool_status():
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalid()
    }
```

## 모니터링 및 로깅

### 1. 쿼리 성능 모니터링
```python
import time
from sqlalchemy import event

@event.listens_for(engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()

@event.listens_for(engine, "after_cursor_execute")
def receive_after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - context._query_start_time
    if total > 1.0:  # 1초 이상 쿼리 로깅
        logger.warning(f"Slow query: {total:.2f}s - {statement}")
```

### 2. 데이터베이스 헬스체크
```python
def db_health_check():
    """데이터베이스 연결 상태 확인"""
    try:
        session = SessionLocal()
        session.execute("SELECT 1")
        session.close()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
```

## 에러 처리

### 1. 연결 오류 처리
```python
from sqlalchemy.exc import OperationalError
import time

def retry_db_operation(func, max_retries=3, delay=1):
    """데이터베이스 작업 재시도"""
    for attempt in range(max_retries):
        try:
            return func()
        except OperationalError as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"DB operation failed, retrying in {delay}s: {e}")
            time.sleep(delay)
            delay *= 2  # 지수적 백오프
```

### 2. 데이터 무결성 검증
```python
def validate_price_data(price: Decimal, confidence: Decimal) -> bool:
    """가격 데이터 유효성 검증"""
    if price <= 0:
        return False
    if not (0 <= confidence <= 1):
        return False
    return True

def validate_before_insert(data: dict) -> bool:
    """삽입 전 데이터 검증"""
    required_fields = ['product_id', 'price', 'confidence_score']
    return all(field in data for field in required_fields)
```

## 마이그레이션 관리

### Alembic 설정 (향후 구현)
```python
# alembic/env.py
from models.base import Base
from models import *  # 모든 모델 임포트

target_metadata = Base.metadata
```

### 스키마 변경 시 주의사항
1. **하위 호환성**: 기존 크롤러 코드가 정상 동작하도록 보장
2. **데이터 마이그레이션**: 기존 데이터 손실 방지
3. **인덱스 관리**: 성능 영향 최소화
4. **API 서버 동기화**: NestJS 서버와 스키마 동기화