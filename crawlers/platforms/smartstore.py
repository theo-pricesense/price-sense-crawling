"""
Naver Smart Store platform crawler implementation.

This module implements the crawler for Naver Smart Store (smartstore.naver.com),
which is React-based and requires JavaScript rendering.
"""

import json
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


class SmartStoreCrawler(BaseCrawler):
    """네이버 스마트스토어 전용 크롤러"""
    
    def __init__(self, **kwargs):
        super().__init__(platform=PlatformType.SMART_STORE, **kwargs)
        
        # 스마트스토어 특화 설정 (React 기반이라 더 느림)
        self.request_delay = 3.0
        self.timeout = 40  # 더 긴 대기시간
        
    def _is_platform_url(self, url: str) -> bool:
        """스마트스토어 URL인지 확인"""
        try:
            parsed = urlparse(url)
            return 'smartstore.naver.com' in parsed.netloc.lower()
        except Exception:
            return False
    
    def get_platform_selectors(self) -> Dict[str, str]:
        """스마트스토어 플랫폼 CSS 셀렉터"""
        return {
            # 상품명
            'product_name': [
                '.ProductTitle__title___2-5QT',
                '._2huTLaXgWw',
                '.ProductTitle-module__title',
                '.product_name h2',
                'h2[class*="ProductTitle"]'
            ],
            
            # 현재 가격
            'current_price': [
                '.ProductPrice__value___2e-5e',
                '._1Z7oH6yCQ0',
                '.ProductPrice-module__value',
                '.price .num strong',
                '[class*="ProductPrice"] [class*="value"]'
            ],
            
            # 원래 가격
            'original_price': [
                '.ProductPrice__origin___3QKJe',
                '.origin_price .num',
                '[class*="ProductPrice"] [class*="origin"]'
            ],
            
            # 할인율
            'discount_rate': [
                '.ProductPrice__discount___1KEbP',
                '.discount_rate',
                '[class*="ProductPrice"] [class*="discount"]'
            ],
            
            # 옵션/재고 영역
            'option_area': [
                '.ProductOption__option___3_W4I',
                '.OptionList__option___2a3xh',
                '.product_option_area',
                '[class*="ProductOption"]'
            ],
            
            # 구매 버튼
            'buy_button': [
                '.Button__button___3-8uJ[class*="primary"]',
                '.ProductButton__button___2oUJl',
                '.buy_button',
                '[class*="ProductButton"]'
            ],
            
            # 품절 표시
            'out_of_stock': [
                '.ProductButton__soldout___-8PpF',
                '.soldout',
                '[class*="soldout"]',
                '[class*="SoldOut"]'
            ],
            
            # 상품 이미지
            'image': [
                '.ProductImage__image___1TmPp img',
                '.product_image img',
                '[class*="ProductImage"] img',
                '.thumb_area img'
            ],
            
            # 브랜드/스토어명
            'brand': [
                '.ProductBrand__name___1b2fq',
                '.brand_name',
                '.store_name',
                '[class*="ProductBrand"]'
            ],
            
            # 카테고리 (breadcrumb)
            'category': [
                '.Breadcrumb__item___1-Hha',
                '.breadcrumb_item',
                '[class*="Breadcrumb"]'
            ],
            
            # 평점
            'rating': [
                '.ProductReview__rating___12_qJ',
                '.review_rating .num',
                '[class*="ProductReview"] [class*="rating"]'
            ],
            
            # 리뷰 수
            'review_count': [
                '.ProductReview__count___h8aEB',
                '.review_count',
                '[class*="ProductReview"] [class*="count"]'
            ],
            
            # 배송 정보
            'shipping': [
                '.ProductDelivery__info___3hHJM',
                '.delivery_info',
                '[class*="ProductDelivery"]'
            ]
        }
    
    async def extract_product_data(self, product_id: str, url: str) -> CrawlResult:
        """스마트스토어 상품 데이터 추출"""
        if not self.driver:
            self.driver = self._init_webdriver()
        
        try:
            self.driver.get(url)
            
            # React 앱 로딩 완료 대기
            WebDriverWait(self.driver, self.timeout).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="ProductTitle"]')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.product_name h2')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, '._2huTLaXgWw'))
                )
            )
            
            # 추가 로딩 대기 (동적 컨텐츠)
            import asyncio
            await asyncio.sleep(2)
            
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
            
            # 재고 상태 확인
            data['stock_status'] = self._extract_stock_status()
            
            # 이미지 URL
            data['image_url'] = self._extract_image_url(selectors['image'])
            
            # 브랜드/스토어명
            data['brand'] = self._extract_text_by_selectors(selectors['brand'])
            
            # 카테고리
            data['category'] = self._extract_category()
            
            # 평점
            rating_text = self._extract_text_by_selectors(selectors['rating'])
            data['rating'] = self._extract_rating(rating_text) if rating_text else None
            
            # 배송 정보
            data['promotion_info'] = self._extract_text_by_selectors(selectors['shipping'])
            
            # 구조화된 데이터에서 추가 정보 추출
            structured_data = self._extract_structured_data_from_page()
            if structured_data:
                data.update(structured_data)
            
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
            self.logger.error(f"Timeout loading SmartStore page: {url}")
            return CrawlResult(
                success=False,
                product_id=product_id,
                platform=self.platform,
                url=url,
                error_message="페이지 로드 시간 초과 (React 앱 로딩 실패)"
            )
            
        except Exception as e:
            self.logger.error(f"Error extracting SmartStore data: {e}")
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
                if text and text != '':
                    return text
            except NoSuchElementException:
                continue
        return None
    
    def _extract_stock_status(self) -> StockStatus:
        """재고 상태 추출"""
        try:
            # 품절 표시 확인
            selectors = self.get_platform_selectors()
            
            for selector in selectors['out_of_stock']:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed():
                        return StockStatus.OUT_OF_STOCK
                except NoSuchElementException:
                    continue
            
            # 구매 버튼 상태 확인
            for selector in selectors['buy_button']:
                try:
                    buy_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    
                    # 버튼 텍스트 확인
                    button_text = buy_button.text.lower()
                    if any(word in button_text for word in ['품절', 'soldout', '판매종료']):
                        return StockStatus.OUT_OF_STOCK
                    elif '구매하기' in button_text or 'buy' in button_text:
                        if buy_button.is_enabled():
                            return StockStatus.AVAILABLE
                        else:
                            return StockStatus.OUT_OF_STOCK
                    
                except NoSuchElementException:
                    continue
            
            # 옵션 영역에서 재고 정보 확인
            for selector in self.get_platform_selectors()['option_area']:
                try:
                    option_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for option in option_elements:
                        option_text = option.text.lower()
                        if '품절' in option_text or 'soldout' in option_text:
                            return StockStatus.LIMITED  # 일부 옵션 품절
                        elif '재고부족' in option_text:
                            return StockStatus.CRITICAL
                except NoSuchElementException:
                    continue
            
            # 기본값은 구매 가능으로 간주
            return StockStatus.AVAILABLE
            
        except Exception:
            return StockStatus.UNKNOWN
    
    def _extract_image_url(self, selectors: list) -> Optional[str]:
        """이미지 URL 추출"""
        for selector in selectors:
            try:
                img_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                img_url = img_element.get_attribute('src')
                
                # lazy loading 이미지 처리
                if not img_url or 'data:image' in img_url:
                    img_url = img_element.get_attribute('data-src')
                
                if img_url and img_url.startswith('http'):
                    return img_url
                    
            except NoSuchElementException:
                continue
        return None
    
    def _extract_category(self) -> Optional[str]:
        """카테고리 정보 추출 (breadcrumb)"""
        try:
            selectors = self.get_platform_selectors()['category']
            categories = []
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and text not in categories:
                            categories.append(text)
                    
                    if categories:
                        return ' > '.join(categories)
                        
                except NoSuchElementException:
                    continue
            
        except Exception:
            pass
        
        return None
    
    def _extract_structured_data_from_page(self) -> Dict:
        """페이지에서 구조화된 데이터 추출"""
        try:
            # JSON-LD 스크립트 태그 찾기
            scripts = self.driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]')
            
            for script in scripts:
                try:
                    script_content = script.get_attribute('innerHTML')
                    if script_content:
                        data = json.loads(script_content)
                        
                        if isinstance(data, dict) and data.get('@type') == 'Product':
                            return self._parse_structured_product_data(data)
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and item.get('@type') == 'Product':
                                    return self._parse_structured_product_data(item)
                                    
                except (json.JSONDecodeError, Exception):
                    continue
            
            # Next.js 앱의 초기 상태 데이터 확인
            try:
                next_data_script = self.driver.find_element(
                    By.CSS_SELECTOR, 'script#__NEXT_DATA__'
                )
                if next_data_script:
                    next_data = json.loads(next_data_script.get_attribute('innerHTML'))
                    return self._parse_next_data(next_data)
                    
            except (NoSuchElementException, json.JSONDecodeError):
                pass
            
        except Exception as e:
            self.logger.debug(f"구조화된 데이터 추출 실패: {e}")
        
        return {}
    
    def _parse_structured_product_data(self, data: dict) -> Dict:
        """구조화된 상품 데이터 파싱"""
        parsed = {}
        
        try:
            # 상품명
            if 'name' in data and not parsed.get('product_name'):
                parsed['product_name'] = data['name']
            
            # 가격 정보
            offers = data.get('offers', {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            
            if 'price' in offers:
                price_text = str(offers['price'])
                parsed['price'] = self._extract_price(price_text)
            
            # 이미지
            if 'image' in data:
                image = data['image']
                if isinstance(image, list):
                    image = image[0] if image else None
                if isinstance(image, dict):
                    image = image.get('url')
                if image:
                    parsed['image_url'] = image
            
            # 브랜드
            if 'brand' in data:
                brand = data['brand']
                if isinstance(brand, dict):
                    brand = brand.get('name')
                if brand:
                    parsed['brand'] = brand
            
            # 평점
            rating_data = data.get('aggregateRating', {})
            if rating_data and 'ratingValue' in rating_data:
                try:
                    parsed['rating'] = float(rating_data['ratingValue'])
                except (ValueError, TypeError):
                    pass
                    
        except Exception as e:
            self.logger.debug(f"구조화된 데이터 파싱 오류: {e}")
        
        return parsed
    
    def _parse_next_data(self, next_data: dict) -> Dict:
        """Next.js 초기 데이터에서 상품 정보 추출"""
        try:
            props = next_data.get('props', {})
            page_props = props.get('pageProps', {})
            
            # 상품 정보가 있는 경우
            if 'product' in page_props:
                product = page_props['product']
                return self._extract_from_product_object(product)
                
        except Exception as e:
            self.logger.debug(f"Next.js 데이터 파싱 오류: {e}")
        
        return {}
    
    def _extract_from_product_object(self, product: dict) -> Dict:
        """상품 객체에서 데이터 추출"""
        parsed = {}
        
        try:
            if 'name' in product:
                parsed['product_name'] = product['name']
            
            if 'price' in product:
                parsed['price'] = self._extract_price(str(product['price']))
            
            if 'imageUrl' in product or 'image' in product:
                image = product.get('imageUrl') or product.get('image')
                if image:
                    parsed['image_url'] = image
                    
        except Exception:
            pass
        
        return parsed
    
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