"""
Base crawler class for all platform-specific crawlers.

This module provides the abstract base class that all platform-specific crawlers
must inherit from. It defines the common interface and shared functionality
for web scraping operations.
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy.orm import Session

from models.base import PlatformType, StockStatus
from models.price_history import PriceHistory
from models.product import Product
from models.scrape_logs import ProductScrapeLog
from models.stock_history import StockHistory
from storage.connection import SessionLocal
from utils.logging import get_logger


class CrawlResult:
    """크롤링 결과를 담는 데이터 클래스"""
    
    def __init__(
        self,
        success: bool,
        product_id: str,
        platform: PlatformType,
        url: str,
        product_name: Optional[str] = None,
        price: Optional[Decimal] = None,
        original_price: Optional[Decimal] = None,
        discount_rate: Optional[float] = None,
        stock_status: StockStatus = StockStatus.UNKNOWN,
        stock_quantity: Optional[int] = None,
        promotion_info: Optional[str] = None,
        image_url: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        rating: Optional[float] = None,
        review_count: Optional[int] = None,
        confidence_score: float = 0.0,
        error_message: Optional[str] = None,
        execution_time: Optional[float] = None
    ):
        self.success = success
        self.product_id = product_id
        self.platform = platform
        self.url = url
        self.product_name = product_name
        self.price = price
        self.original_price = original_price
        self.discount_rate = discount_rate
        self.stock_status = stock_status
        self.stock_quantity = stock_quantity
        self.promotion_info = promotion_info
        self.image_url = image_url
        self.category = category
        self.brand = brand
        self.rating = rating
        self.review_count = review_count
        self.confidence_score = confidence_score
        self.error_message = error_message
        self.execution_time = execution_time
        self.scraped_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """결과를 딕셔너리로 변환"""
        return {
            "success": self.success,
            "product_id": self.product_id,
            "platform": self.platform.value,
            "url": self.url,
            "product_name": self.product_name,
            "price": float(self.price) if self.price else None,
            "original_price": float(self.original_price) if self.original_price else None,
            "discount_rate": self.discount_rate,
            "stock_status": self.stock_status.value,
            "stock_quantity": self.stock_quantity,
            "promotion_info": self.promotion_info,
            "image_url": self.image_url,
            "category": self.category,
            "brand": self.brand,
            "rating": self.rating,
            "review_count": self.review_count,
            "confidence_score": self.confidence_score,
            "error_message": self.error_message,
            "execution_time": self.execution_time,
            "scraped_at": self.scraped_at.isoformat()
        }


class BaseCrawler(ABC):
    """모든 플랫폼 크롤러의 기본 클래스"""
    
    def __init__(
        self,
        platform: PlatformType,
        headless: bool = True,
        request_delay: float = 2.0,
        timeout: int = 30,
        max_retries: int = 3,
        user_agent: Optional[str] = None
    ):
        self.platform = platform
        self.headless = headless
        self.request_delay = request_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = get_logger(f"crawler.{platform.value}")
        
        # User-Agent 설정
        self.ua = UserAgent()
        self.user_agent = user_agent or self.ua.random
        
        # WebDriver 및 HTTP 클라이언트 초기화
        self.driver: Optional[webdriver.Chrome] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        
        # 성능 메트릭
        self.request_count = 0
        self.error_count = 0
        self.start_time = time.time()
    
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        await self.cleanup()
    
    async def initialize(self):
        """크롤러 초기화"""
        try:
            # HTTP 클라이언트 초기화
            self.http_client = httpx.AsyncClient(
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
                follow_redirects=True
            )
            
            self.logger.info(f"{self.platform.value} crawler initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize crawler: {e}")
            raise
    
    async def cleanup(self):
        """리소스 정리"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
            
            if self.http_client:
                await self.http_client.aclose()
                self.http_client = None
            
            self.logger.info(f"{self.platform.value} crawler cleaned up")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def _init_webdriver(self) -> webdriver.Chrome:
        """Selenium WebDriver 초기화"""
        try:
            chrome_options = ChromeOptions()
            
            if self.headless:
                chrome_options.add_argument("--headless")
            
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-logging")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            chrome_options.add_argument("--disable-renderer-backgrounding")
            chrome_options.add_argument(f"--user-agent={self.user_agent}")
            
            # 메모리 사용량 최적화
            chrome_options.add_argument("--memory-pressure-off")
            chrome_options.add_argument("--max_old_space_size=4096")
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(self.timeout)
            driver.implicitly_wait(10)
            
            return driver
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver: {e}")
            raise
    
    async def _delay(self):
        """요청 간 지연"""
        if self.request_delay > 0:
            await asyncio.sleep(self.request_delay)
    
    async def scrape_product(self, product_id: str, url: str) -> CrawlResult:
        """상품 정보 크롤링 메인 메서드"""
        start_time = time.time()
        self.request_count += 1
        
        try:
            self.logger.info(f"Starting scrape for product {product_id}: {url}")
            
            # URL 유효성 검사
            if not self._is_valid_url(url):
                raise ValueError(f"Invalid URL: {url}")
            
            # 플랫폼 URL 검증
            if not self._is_platform_url(url):
                raise ValueError(f"URL does not belong to {self.platform.value}: {url}")
            
            # 실제 크롤링 실행
            result = await self._scrape_with_retry(product_id, url)
            
            # 실행 시간 기록
            result.execution_time = time.time() - start_time
            
            # 데이터베이스 저장
            if result.success and result.confidence_score >= 0.7:
                await self._save_result(result)
            
            self.logger.info(
                f"Scrape completed for product {product_id}: "
                f"success={result.success}, "
                f"confidence={result.confidence_score:.2f}, "
                f"time={result.execution_time:.2f}s"
            )
            
            return result
            
        except Exception as e:
            self.error_count += 1
            execution_time = time.time() - start_time
            
            self.logger.error(f"Scrape failed for product {product_id}: {e}")
            
            return CrawlResult(
                success=False,
                product_id=product_id,
                platform=self.platform,
                url=url,
                error_message=str(e),
                execution_time=execution_time
            )
    
    async def _scrape_with_retry(self, product_id: str, url: str) -> CrawlResult:
        """재시도 로직이 포함된 크롤링"""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                await self._delay()
                result = await self.extract_product_data(product_id, url)
                return result
                
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"Scrape attempt {attempt + 1}/{self.max_retries} failed "
                    f"for product {product_id}: {e}"
                )
                
                if attempt < self.max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    await asyncio.sleep(wait_time)
        
        raise last_exception
    
    @abstractmethod
    async def extract_product_data(self, product_id: str, url: str) -> CrawlResult:
        """
        플랫폼별 상품 데이터 추출 메서드
        
        각 플랫폼 크롤러에서 구현해야 함
        """
        pass
    
    @abstractmethod
    def _is_platform_url(self, url: str) -> bool:
        """플랫폼 URL 검증"""
        pass
    
    @abstractmethod
    def get_platform_selectors(self) -> Dict[str, str]:
        """플랫폼별 CSS 셀렉터 반환"""
        pass
    
    def _is_valid_url(self, url: str) -> bool:
        """URL 유효성 검사"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def _extract_price(self, price_text: str) -> Optional[Decimal]:
        """가격 텍스트에서 숫자 추출"""
        try:
            import re
            price_str = re.sub(r'[^\d,.]', '', price_text)
            price_str = price_str.replace(',', '')
            return Decimal(price_str)
        except (ValueError, TypeError):
            return None
    
    def _calculate_confidence_score(self, data: Dict[str, Any]) -> float:
        """데이터 품질에 따른 신뢰도 점수 계산"""
        score = 0.0
        total_checks = 5
        
        # 상품명 존재 여부 (20%)
        if data.get('product_name'):
            score += 0.2
        
        # 가격 정보 존재 여부 (30%)
        if data.get('price') is not None:
            score += 0.3
        
        # 재고 상태 확인 가능 여부 (20%)
        if data.get('stock_status') != StockStatus.UNKNOWN:
            score += 0.2
        
        # 이미지 URL 존재 여부 (15%)
        if data.get('image_url'):
            score += 0.15
        
        # 추가 정보 (프로모션, 카테고리 등) 존재 여부 (15%)
        additional_info = sum([
            bool(data.get('promotion_info')),
            bool(data.get('category')),
            bool(data.get('brand'))
        ])
        score += (additional_info / 3) * 0.15
        
        return round(score, 2)
    
    async def _save_result(self, result: CrawlResult):
        """크롤링 결과를 데이터베이스에 저장"""
        session = SessionLocal()
        
        try:
            # 가격 이력 저장
            if result.price is not None:
                price_history = PriceHistory(
                    product_id=result.product_id,
                    price=result.price,
                    original_price=result.original_price,
                    discount_rate=result.discount_rate,
                    confidence_score=Decimal(str(result.confidence_score)),
                    recorded_at=result.scraped_at
                )
                session.add(price_history)
            
            # 재고 이력 저장
            stock_history = StockHistory(
                product_id=result.product_id,
                stock_status=result.stock_status,
                stock_quantity=result.stock_quantity,
                confidence_score=Decimal(str(result.confidence_score)),
                recorded_at=result.scraped_at
            )
            session.add(stock_history)
            
            # 스크래핑 로그 저장
            scrape_log = ProductScrapeLog(
                product_id=result.product_id,
                platform=result.platform,
                url=result.url,
                status="success" if result.success else "failed",
                execution_time=result.execution_time,
                confidence_score=Decimal(str(result.confidence_score)),
                error_message=result.error_message,
                scraped_data=json.dumps(result.to_dict(), ensure_ascii=False, default=str)
            )
            session.add(scrape_log)
            
            session.commit()
            self.logger.debug(f"Saved crawl result for product {result.product_id}")
            
        except Exception as e:
            session.rollback()
            self.logger.error(f"Failed to save crawl result: {e}")
            raise
        finally:
            session.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """크롤러 성능 통계 반환"""
        runtime = time.time() - self.start_time
        success_rate = ((self.request_count - self.error_count) / self.request_count 
                       if self.request_count > 0 else 0)
        
        return {
            "platform": self.platform.value,
            "runtime": runtime,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "success_rate": success_rate,
            "avg_request_time": runtime / self.request_count if self.request_count > 0 else 0
        }