"""
Naver Shopping platform crawler implementation.

This module implements the crawler for Naver Shopping (shopping.naver.com),
which often provides structured data and can be scraped with HTTP requests.
"""

import json
import re
from decimal import Decimal
from typing import Dict, Optional
from urllib.parse import urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from crawlers.core.base_crawler import BaseCrawler, CrawlResult
from models.base import PlatformType, StockStatus


class NaverShoppingCrawler(BaseCrawler):
    """네이버쇼핑 전용 크롤러"""
    
    def __init__(self, **kwargs):
        super().__init__(platform=PlatformType.NAVER_SHOPPING, **kwargs)
        
        # 네이버쇼핑 특화 설정
        self.request_delay = 2.0
        
    def _is_platform_url(self, url: str) -> bool:
        """네이버쇼핑 URL인지 확인"""
        try:
            parsed = urlparse(url)
            return 'shopping.naver.com' in parsed.netloc.lower()
        except Exception:
            return False
    
    def get_platform_selectors(self) -> Dict[str, str]:
        """네이버쇼핑 플랫폼 CSS 셀렉터"""
        return {
            # 상품명
            'product_name': [
                '.product_title',
                '.prod_tit',
                'h2.product_name',
                '.product_info .title'
            ],
            
            # 현재 가격
            'current_price': [
                '.price_num',
                '.sale_price .price',
                '.product_price .num',
                '.price_area .price'
            ],
            
            # 원래 가격
            'original_price': [
                '.origin_price .price',
                '.before_price .price',
                '.product_price .origin_price'
            ],
            
            # 할인율
            'discount_rate': [
                '.discount_rate',
                '.sale_rate',
                '.discount_percent'
            ],
            
            # 배송비/배송 정보
            'shipping': [
                '.delivery_info',
                '.shipping_fee',
                '.delivery_fee'
            ],
            
            # 상품 이미지
            'image': [
                '.product_image img',
                '.prod_img img',
                '.thumb_area img'
            ],
            
            # 카테고리
            'category': [
                '.product_category',
                '.category_info',
                '.breadcrumb'
            ],
            
            # 브랜드/쇼핑몰
            'brand': [
                '.brand',
                '.shop_name',
                '.seller_name'
            ],
            
            # 평점
            'rating': [
                '.rating_num',
                '.score_num',
                '.review_point'
            ],
            
            # 리뷰 수
            'review_count': [
                '.review_count',
                '.count_num'
            ]
        }
    
    async def extract_product_data(self, product_id: str, url: str) -> CrawlResult:
        """네이버쇼핑 상품 데이터 추출"""
        
        # 먼저 HTTP 요청으로 시도 (더 빠름)
        try:
            result = await self._extract_with_http(product_id, url)
            if result.success:
                return result
        except Exception as e:
            self.logger.info(f"HTTP 추출 실패, Selenium으로 시도: {e}")
        
        # HTTP 실패시 Selenium 사용
        return await self._extract_with_selenium(product_id, url)
    
    async def _extract_with_http(self, product_id: str, url: str) -> CrawlResult:
        """HTTP 요청을 통한 데이터 추출"""
        if not self.http_client:
            await self.initialize()
        
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 구조화된 데이터 찾기 (JSON-LD)
            structured_data = self._extract_structured_data(soup)
            if structured_data:
                return self._parse_structured_data(structured_data, product_id, url)
            
            # 일반 HTML 파싱
            return self._parse_html_content(soup, product_id, url)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise Exception("접근 차단됨 - Selenium 필요")
            raise
    
    async def _extract_with_selenium(self, product_id: str, url: str) -> CrawlResult:
        """Selenium을 통한 데이터 추출"""
        if not self.driver:
            self.driver = self._init_webdriver()
        
        try:
            self.driver.get(url)
            
            # 페이지 로드 완료 대기
            WebDriverWait(self.driver, self.timeout).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "product_title")),
                    EC.presence_of_element_located((By.CLASS_NAME, "prod_tit"))
                )
            )
            
            data = {}
            selectors = self.get_platform_selectors()
            
            # 상품명
            data['product_name'] = self._extract_text_by_selectors(selectors['product_name'])
            
            # 가격 정보
            current_price_text = self._extract_text_by_selectors(selectors['current_price'])
            data['price'] = self._extract_price(current_price_text) if current_price_text else None
            
            original_price_text = self._extract_text_by_selectors(selectors['original_price'])
            data['original_price'] = self._extract_price(original_price_text) if original_price_text else None
            
            # 할인율
            discount_text = self._extract_text_by_selectors(selectors['discount_rate'])
            data['discount_rate'] = self._extract_discount_rate(discount_text) if discount_text else None
            
            # 재고는 네이버쇼핑에서 명시적으로 표시되지 않으므로 구매 가능으로 간주
            data['stock_status'] = StockStatus.AVAILABLE
            
            # 배송 정보
            data['promotion_info'] = self._extract_text_by_selectors(selectors['shipping'])
            
            # 이미지
            data['image_url'] = self._extract_image_url(selectors['image'])
            
            # 카테고리
            data['category'] = self._extract_text_by_selectors(selectors['category'])
            
            # 브랜드
            data['brand'] = self._extract_text_by_selectors(selectors['brand'])
            
            # 평점
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
                stock_status=data.get('stock_status', StockStatus.AVAILABLE),
                promotion_info=data.get('promotion_info'),
                image_url=data.get('image_url'),
                category=data.get('category'),
                brand=data.get('brand'),
                rating=data.get('rating'),
                confidence_score=confidence_score
            )
            
        except TimeoutException:
            return CrawlResult(
                success=False,
                product_id=product_id,
                platform=self.platform,
                url=url,
                error_message="페이지 로드 시간 초과"
            )
        except Exception as e:
            return CrawlResult(
                success=False,
                product_id=product_id,
                platform=self.platform,
                url=url,
                error_message=str(e)
            )
    
    def _extract_structured_data(self, soup: BeautifulSoup) -> Optional[dict]:
        """구조화된 데이터 추출 (JSON-LD)"""
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    return data
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('@type') == 'Product':
                            return item
        except (json.JSONDecodeError, AttributeError):
            pass
        return None
    
    def _parse_structured_data(self, data: dict, product_id: str, url: str) -> CrawlResult:
        """구조화된 데이터 파싱"""
        try:
            product_name = data.get('name')
            
            # 가격 정보
            offers = data.get('offers', {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            
            price_text = str(offers.get('price', ''))
            price = self._extract_price(price_text) if price_text else None
            
            # 이미지
            image_url = data.get('image')
            if isinstance(image_url, list):
                image_url = image_url[0] if image_url else None
            
            # 브랜드
            brand_info = data.get('brand', {})
            brand = brand_info.get('name') if isinstance(brand_info, dict) else str(brand_info)
            
            # 평점
            rating_info = data.get('aggregateRating', {})
            rating = None
            if rating_info:
                rating_value = rating_info.get('ratingValue')
                if rating_value:
                    rating = float(rating_value)
            
            confidence_score = self._calculate_confidence_score({
                'product_name': product_name,
                'price': price,
                'image_url': image_url,
                'brand': brand,
                'rating': rating
            })
            
            return CrawlResult(
                success=True,
                product_id=product_id,
                platform=self.platform,
                url=url,
                product_name=product_name,
                price=price,
                stock_status=StockStatus.AVAILABLE,
                image_url=image_url,
                brand=brand,
                rating=rating,
                confidence_score=confidence_score
            )
            
        except Exception as e:
            raise Exception(f"구조화된 데이터 파싱 실패: {e}")
    
    def _parse_html_content(self, soup: BeautifulSoup, product_id: str, url: str) -> CrawlResult:
        """일반 HTML 컨텐츠 파싱"""
        data = {}
        
        # 상품명
        for selector in self.get_platform_selectors()['product_name']:
            element = soup.select_one(selector)
            if element:
                data['product_name'] = element.get_text(strip=True)
                break
        
        # 가격
        for selector in self.get_platform_selectors()['current_price']:
            element = soup.select_one(selector)
            if element:
                price_text = element.get_text(strip=True)
                data['price'] = self._extract_price(price_text)
                break
        
        # 이미지
        for selector in self.get_platform_selectors()['image']:
            element = soup.select_one(selector)
            if element:
                data['image_url'] = element.get('src')
                break
        
        confidence_score = self._calculate_confidence_score(data)
        
        return CrawlResult(
            success=True,
            product_id=product_id,
            platform=self.platform,
            url=url,
            product_name=data.get('product_name'),
            price=data.get('price'),
            stock_status=StockStatus.AVAILABLE,
            image_url=data.get('image_url'),
            confidence_score=confidence_score
        )
    
    def _extract_text_by_selectors(self, selectors: list) -> Optional[str]:
        """여러 셀렉터를 시도해서 텍스트 추출 (Selenium용)"""
        for selector in selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = element.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue
        return None
    
    def _extract_image_url(self, selectors: list) -> Optional[str]:
        """이미지 URL 추출 (Selenium용)"""
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
        """할인율 추출"""
        try:
            rate_match = re.search(r'(\d+(?:\.\d+)?)%', discount_text)
            if rate_match:
                return float(rate_match.group(1))
        except (ValueError, AttributeError):
            pass
        return None
    
    def _extract_rating(self, rating_text: str) -> Optional[float]:
        """평점 추출"""
        try:
            rating_match = re.search(r'(\d+(?:\.\d+)?)', rating_text)
            if rating_match:
                rating = float(rating_match.group(1))
                if 0 <= rating <= 5:
                    return rating
        except (ValueError, AttributeError):
            pass
        return None