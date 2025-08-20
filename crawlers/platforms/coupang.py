"""
Coupang platform crawler implementation.

This module implements the crawler for Coupang (coupang.com), 
one of Korea's largest e-commerce platforms.
"""

import re
from decimal import Decimal
from typing import Dict, Optional
from urllib.parse import urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from crawlers.core.base_crawler import BaseCrawler, CrawlResult
from models.base import PlatformType, StockStatus


class CoupangCrawler(BaseCrawler):
    """쿠팡 전용 크롤러"""
    
    def __init__(self, **kwargs):
        super().__init__(platform=PlatformType.COUPANG, **kwargs)
        
        # 쿠팡 특화 설정
        self.request_delay = 3.0  # 쿠팡은 좀 더 긴 지연
        
    def _is_platform_url(self, url: str) -> bool:
        """쿠팡 URL인지 확인"""
        try:
            parsed = urlparse(url)
            return 'coupang.com' in parsed.netloc.lower()
        except Exception:
            return False
    
    def get_platform_selectors(self) -> Dict[str, str]:
        """쿠팡 플랫폼 CSS 셀렉터"""
        return {
            # 상품명
            'product_name': [
                '.prod-buy-header__title',
                '.product-title h2',
                '.prod-buy-header .title'
            ],
            
            # 현재 가격
            'current_price': [
                '.total-price strong.price-value',
                '.price .total-price .price-value', 
                '.prod-price .total-price .price-value',
                '.price-wrap .total-price'
            ],
            
            # 원래 가격 (할인 전)
            'original_price': [
                '.origin-price .price-value',
                '.prod-origin-price .price-value',
                '.price-wrap .origin-price'
            ],
            
            # 할인율
            'discount_rate': [
                '.discount-percentage',
                '.prod-coupon-price .discount-percentage'
            ],
            
            # 재고 상태
            'stock_status': [
                '.prod-option-inventory',
                '.inventory-notice', 
                '.out-of-stock',
                '.stock-info'
            ],
            
            # 배송/프로모션 정보
            'promotion': [
                '.badge.rocket',
                '.prod-shipping-fee-and-pdd-arrival-info',
                '.shipping-fee-info',
                '.badge-list .badge'
            ],
            
            # 상품 이미지
            'image': [
                '.prod-image__detail img',
                '.prod-image-container img',
                '.product-image img'
            ],
            
            # 카테고리
            'category': [
                '.prod-navigation__list',
                '.breadcrumb-list'
            ],
            
            # 브랜드
            'brand': [
                '.prod-sale-vendor-name',
                '.brand-name'
            ],
            
            # 평점
            'rating': [
                '.rating-star-num',
                '.prod-review-average-rating'
            ]
        }
    
    async def extract_product_data(self, product_id: str, url: str) -> CrawlResult:
        """쿠팡 상품 데이터 추출"""
        if not self.driver:
            self.driver = self._init_webdriver()
        
        try:
            # 페이지 로드
            self.driver.get(url)
            
            # 페이지 로드 완료 대기
            WebDriverWait(self.driver, self.timeout).until(
                EC.presence_of_element_located((By.CLASS_NAME, "prod-buy-header"))
            )
            
            # 데이터 추출
            data = {}
            selectors = self.get_platform_selectors()
            
            # 상품명 추출
            data['product_name'] = self._extract_text_by_selectors(selectors['product_name'])
            
            # 가격 정보 추출
            current_price_text = self._extract_text_by_selectors(selectors['current_price'])
            data['price'] = self._extract_price(current_price_text) if current_price_text else None
            
            original_price_text = self._extract_text_by_selectors(selectors['original_price'])
            data['original_price'] = self._extract_price(original_price_text) if original_price_text else None
            
            # 할인율 추출
            discount_text = self._extract_text_by_selectors(selectors['discount_rate'])
            data['discount_rate'] = self._extract_discount_rate(discount_text) if discount_text else None
            
            # 재고 상태 추출
            data['stock_status'] = self._extract_stock_status()
            
            # 프로모션 정보 추출
            data['promotion_info'] = self._extract_promotion_info(selectors['promotion'])
            
            # 이미지 URL 추출
            data['image_url'] = self._extract_image_url(selectors['image'])
            
            # 카테고리 추출
            data['category'] = self._extract_text_by_selectors(selectors['category'])
            
            # 브랜드 추출
            data['brand'] = self._extract_text_by_selectors(selectors['brand'])
            
            # 평점 추출
            rating_text = self._extract_text_by_selectors(selectors['rating'])
            data['rating'] = self._extract_rating(rating_text) if rating_text else None
            
            # 신뢰도 점수 계산
            confidence_score = self._calculate_confidence_score(data)
            
            return CrawlResult(
                success=True,
                product_id=product_id,
                platform=self.platform,
                url=url,
                product_name=data.get('product_name'),
                price=data.get('price'),
                original_price=data.get('original_price'),
                discount_rate=data.get('discount_rate'),
                stock_status=data.get('stock_status', StockStatus.UNKNOWN),
                promotion_info=data.get('promotion_info'),
                image_url=data.get('image_url'),
                category=data.get('category'),
                brand=data.get('brand'),
                rating=data.get('rating'),
                confidence_score=confidence_score
            )
            
        except TimeoutException:
            self.logger.error(f"Timeout loading Coupang page: {url}")
            return CrawlResult(
                success=False,
                product_id=product_id,
                platform=self.platform,
                url=url,
                error_message="페이지 로드 시간 초과"
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting Coupang data: {e}")
            return CrawlResult(
                success=False,
                product_id=product_id,
                platform=self.platform,
                url=url,
                error_message=str(e)
            )
    
    def _extract_text_by_selectors(self, selectors: list) -> Optional[str]:
        """여러 셀렉터를 시도해서 텍스트 추출"""
        for selector in selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = element.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue
        return None
    
    def _extract_stock_status(self) -> StockStatus:
        """재고 상태 추출"""
        try:
            # 품절 표시 확인
            out_of_stock_indicators = [
                '.out-of-stock',
                '.sold-out',
                '.temporary-out-of-stock'
            ]
            
            for selector in out_of_stock_indicators:
                try:
                    self.driver.find_element(By.CSS_SELECTOR, selector)
                    return StockStatus.OUT_OF_STOCK
                except NoSuchElementException:
                    continue
            
            # 수량 제한 확인
            try:
                quantity_element = self.driver.find_element(
                    By.CSS_SELECTOR, '.prod-option-inventory, .quantity-info'
                )
                quantity_text = quantity_element.text.lower()
                
                if '품절' in quantity_text or 'out of stock' in quantity_text:
                    return StockStatus.OUT_OF_STOCK
                elif '수량한정' in quantity_text or '한정' in quantity_text:
                    return StockStatus.LIMITED
                elif '재고부족' in quantity_text or '재고 부족' in quantity_text:
                    return StockStatus.CRITICAL
                
            except NoSuchElementException:
                pass
            
            # 구매 버튼 상태 확인
            try:
                buy_button = self.driver.find_element(
                    By.CSS_SELECTOR, '.prod-buy-btn, .buy-button'
                )
                if buy_button.is_enabled() and buy_button.is_displayed():
                    return StockStatus.AVAILABLE
                else:
                    return StockStatus.OUT_OF_STOCK
                    
            except NoSuchElementException:
                pass
            
            return StockStatus.AVAILABLE
            
        except Exception:
            return StockStatus.UNKNOWN
    
    def _extract_promotion_info(self, selectors: list) -> Optional[str]:
        """프로모션 정보 추출"""
        promotions = []
        
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if text and text not in promotions:
                        promotions.append(text)
            except NoSuchElementException:
                continue
        
        return ', '.join(promotions) if promotions else None
    
    def _extract_image_url(self, selectors: list) -> Optional[str]:
        """이미지 URL 추출"""
        for selector in selectors:
            try:
                img_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                img_url = img_element.get_attribute('src')
                if img_url:
                    return img_url
            except NoSuchElementException:
                continue
        return None
    
    def _extract_discount_rate(self, discount_text: str) -> Optional[float]:
        """할인율 추출 (% 형태에서 숫자만)"""
        try:
            # %를 제거하고 숫자만 추출
            rate_match = re.search(r'(\d+(?:\.\d+)?)%', discount_text)
            if rate_match:
                return float(rate_match.group(1))
        except (ValueError, AttributeError):
            pass
        return None
    
    def _extract_rating(self, rating_text: str) -> Optional[float]:
        """평점 추출"""
        try:
            # 숫자와 소수점만 추출
            rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
            if rating_match:
                rating = float(rating_match.group(1))
                # 평점은 보통 5점 만점
                if 0 <= rating <= 5:
                    return rating
        except (ValueError, AttributeError):
            pass
        return None