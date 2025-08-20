"""
Data validation utilities for crawler system.

This module provides validation functions for scraped data, duplicate prevention,
data quality checks, and anomaly detection.
"""

import re
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from urllib.parse import urlparse

from models.base import PlatformType, StockStatus
from storage.redis_client import cache_manager
from utils.logging import get_logger


@dataclass
class ValidationResult:
    """검증 결과"""
    is_valid: bool
    score: float  # 0.0 - 1.0
    errors: List[str]
    warnings: List[str]
    
    def add_error(self, message: str):
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str):
        self.warnings.append(message)


class PriceValidator:
    """가격 데이터 검증"""
    
    def __init__(self):
        self.logger = get_logger("price_validator")
        
        # 플랫폼별 가격 범위 (원)
        self.price_ranges = {
            PlatformType.COUPANG: (100, 10_000_000),
            PlatformType.NAVER_SHOPPING: (100, 5_000_000),
            PlatformType.SMART_STORE: (100, 5_000_000),
            "default": (50, 10_000_000)
        }
        
        # 의심스러운 가격 패턴
        self.suspicious_patterns = [
            r'^1+$',  # 1111... 패턴
            r'^0+$',  # 0000... 패턴
            r'^\d*999+$',  # 999... 패턴
        ]
    
    def validate_price(self, price: Union[str, int, float, Decimal], platform: PlatformType) -> ValidationResult:
        """가격 유효성 검증"""
        result = ValidationResult(True, 1.0, [], [])
        
        if price is None:
            result.add_error("Price is None")
            result.score = 0.0
            return result
        
        try:
            # Decimal로 변환
            if isinstance(price, str):
                # 문자열에서 숫자만 추출
                price_str = re.sub(r'[^\d.]', '', str(price))
                if not price_str:
                    result.add_error("No numeric value found in price string")
                    result.score = 0.0
                    return result
                price_decimal = Decimal(price_str)
            else:
                price_decimal = Decimal(str(price))
            
            # 음수 검증
            if price_decimal < 0:
                result.add_error("Price cannot be negative")
                result.score = 0.0
                return result
            
            # 0원 검증
            if price_decimal == 0:
                result.add_warning("Price is 0 - may indicate unavailable product")
                result.score *= 0.3
            
            # 플랫폼별 가격 범위 검증
            min_price, max_price = self.price_ranges.get(platform, self.price_ranges["default"])
            
            if price_decimal < min_price:
                result.add_warning(f"Price {price_decimal} is below minimum expected ({min_price})")
                result.score *= 0.7
            
            if price_decimal > max_price:
                result.add_warning(f"Price {price_decimal} is above maximum expected ({max_price})")
                result.score *= 0.8
            
            # 의심스러운 패턴 검증
            price_str = str(int(price_decimal))
            for pattern in self.suspicious_patterns:
                if re.match(pattern, price_str):
                    result.add_warning(f"Suspicious price pattern: {price_str}")
                    result.score *= 0.6
                    break
            
            # 소수점 자릿수 검증 (일반적으로 원 단위)
            if price_decimal != price_decimal.quantize(Decimal('1')):
                result.add_warning("Price has decimal places - unusual for KRW")
                result.score *= 0.9
            
        except (ValueError, InvalidOperation) as e:
            result.add_error(f"Invalid price format: {e}")
            result.score = 0.0
        
        return result
    
    def validate_discount_rate(self, discount_rate: Optional[float], current_price: Optional[Decimal], original_price: Optional[Decimal]) -> ValidationResult:
        """할인율 검증"""
        result = ValidationResult(True, 1.0, [], [])
        
        if discount_rate is None:
            return result  # 할인율은 선택사항
        
        # 범위 검증 (0-100%)
        if not (0 <= discount_rate <= 100):
            result.add_error(f"Discount rate {discount_rate}% is out of valid range (0-100%)")
            result.score = 0.0
            return result
        
        # 가격 정보가 있으면 일관성 검증
        if current_price and original_price and current_price > 0 and original_price > 0:
            calculated_rate = ((original_price - current_price) / original_price) * 100
            rate_diff = abs(calculated_rate - discount_rate)
            
            if rate_diff > 5.0:  # 5% 이상 차이나면 경고
                result.add_warning(f"Discount rate mismatch: stated {discount_rate}%, calculated {calculated_rate:.1f}%")
                result.score *= 0.7
        
        # 과도한 할인율 경고
        if discount_rate > 80:
            result.add_warning(f"Very high discount rate: {discount_rate}%")
            result.score *= 0.8
        
        return result


class ProductNameValidator:
    """상품명 검증"""
    
    def __init__(self):
        self.logger = get_logger("product_name_validator")
        
        # 최소/최대 길이
        self.min_length = 3
        self.max_length = 500
        
        # 의심스러운 패턴
        self.invalid_patterns = [
            r'^[\s\-_\.]+$',  # 특수문자만
            r'^[0-9]+$',      # 숫자만
            r'^\w{1,2}$',     # 너무 짧은 단어
        ]
        
        # 금지 키워드 (스팸, 에러 메시지 등)
        self.forbidden_keywords = [
            'error', '에러', '오류', '404', '500',
            'not found', '찾을 수 없', 'unavailable',
            'test', '테스트', 'sample', '샘플'
        ]
    
    def validate_product_name(self, name: Optional[str]) -> ValidationResult:
        """상품명 검증"""
        result = ValidationResult(True, 1.0, [], [])
        
        if not name:
            result.add_error("Product name is empty")
            result.score = 0.0
            return result
        
        name = name.strip()
        
        # 길이 검증
        if len(name) < self.min_length:
            result.add_error(f"Product name too short: {len(name)} < {self.min_length}")
            result.score = 0.0
            return result
        
        if len(name) > self.max_length:
            result.add_warning(f"Product name very long: {len(name)} > {self.max_length}")
            result.score *= 0.9
        
        # 패턴 검증
        for pattern in self.invalid_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                result.add_error(f"Invalid product name pattern: {name}")
                result.score = 0.0
                return result
        
        # 금지 키워드 검증
        name_lower = name.lower()
        for keyword in self.forbidden_keywords:
            if keyword.lower() in name_lower:
                result.add_error(f"Forbidden keyword in product name: {keyword}")
                result.score = 0.0
                return result
        
        # 문자 구성 검증
        alpha_count = sum(1 for c in name if c.isalpha())
        if alpha_count == 0:
            result.add_warning("Product name has no alphabetic characters")
            result.score *= 0.7
        
        return result


class StockStatusValidator:
    """재고 상태 검증"""
    
    def validate_stock_status(self, stock_status: StockStatus, stock_quantity: Optional[int] = None) -> ValidationResult:
        """재고 상태 검증"""
        result = ValidationResult(True, 1.0, [], [])
        
        # 재고 수량과 상태 일관성 검증
        if stock_quantity is not None:
            if stock_quantity < 0:
                result.add_error("Stock quantity cannot be negative")
                result.score = 0.0
                return result
            
            # 수량과 상태 일치 검증
            if stock_quantity == 0 and stock_status == StockStatus.AVAILABLE:
                result.add_warning("Stock quantity is 0 but status is AVAILABLE")
                result.score *= 0.5
            
            if stock_quantity > 0 and stock_status == StockStatus.OUT_OF_STOCK:
                result.add_warning(f"Stock quantity is {stock_quantity} but status is OUT_OF_STOCK")
                result.score *= 0.5
            
            # 수량 범위 검증
            if stock_quantity > 10000:
                result.add_warning(f"Very high stock quantity: {stock_quantity}")
                result.score *= 0.9
        
        return result


class URLValidator:
    """URL 검증"""
    
    def __init__(self):
        self.valid_domains = {
            PlatformType.COUPANG: ['coupang.com', 'www.coupang.com'],
            PlatformType.NAVER_SHOPPING: ['shopping.naver.com'],
            PlatformType.SMART_STORE: ['smartstore.naver.com'],
        }
    
    def validate_url(self, url: str, platform: PlatformType) -> ValidationResult:
        """URL 검증"""
        result = ValidationResult(True, 1.0, [], [])
        
        if not url:
            result.add_error("URL is empty")
            result.score = 0.0
            return result
        
        try:
            parsed = urlparse(url)
            
            # 스킴 검증
            if parsed.scheme not in ['http', 'https']:
                result.add_error(f"Invalid URL scheme: {parsed.scheme}")
                result.score = 0.0
                return result
            
            # HTTPS 권장
            if parsed.scheme == 'http':
                result.add_warning("HTTP URL - HTTPS recommended")
                result.score *= 0.9
            
            # 도메인 검증
            domain = parsed.netloc.lower()
            valid_domains = self.valid_domains.get(platform, [])
            
            if valid_domains and not any(domain.endswith(vd) for vd in valid_domains):
                result.add_error(f"Invalid domain {domain} for platform {platform.value}")
                result.score = 0.0
                return result
            
            # 경로 검증
            if not parsed.path or parsed.path == '/':
                result.add_warning("URL has no specific path")
                result.score *= 0.8
            
        except Exception as e:
            result.add_error(f"URL parsing error: {e}")
            result.score = 0.0
        
        return result


class DuplicateChecker:
    """중복 검증"""
    
    def __init__(self):
        self.logger = get_logger("duplicate_checker")
        self.cache_ttl = 600  # 10분
    
    def _get_cache_key(self, product_id: str) -> str:
        """캐시 키 생성"""
        return f"crawl_history:{product_id}"
    
    def is_recently_crawled(self, product_id: str, threshold_minutes: int = 10) -> bool:
        """최근 크롤링 여부 확인"""
        try:
            cache_key = self._get_cache_key(product_id)
            last_crawl = cache_manager.get(cache_key)
            
            if not last_crawl:
                return False
            
            last_time = datetime.fromisoformat(last_crawl)
            threshold = datetime.utcnow() - timedelta(minutes=threshold_minutes)
            
            return last_time > threshold
            
        except Exception as e:
            self.logger.error(f"Error checking duplicate: {e}")
            return False
    
    def mark_as_crawled(self, product_id: str):
        """크롤링 완료 표시"""
        try:
            cache_key = self._get_cache_key(product_id)
            current_time = datetime.utcnow().isoformat()
            cache_manager.set(cache_key, current_time, self.cache_ttl)
            
        except Exception as e:
            self.logger.error(f"Error marking as crawled: {e}")


class DataValidator:
    """통합 데이터 검증"""
    
    def __init__(self):
        self.logger = get_logger("data_validator")
        self.price_validator = PriceValidator()
        self.name_validator = ProductNameValidator()
        self.stock_validator = StockStatusValidator()
        self.url_validator = URLValidator()
        self.duplicate_checker = DuplicateChecker()
    
    def validate_crawl_data(self, data: Dict[str, Any], product_id: str, url: str, platform: PlatformType) -> ValidationResult:
        """크롤링 데이터 전체 검증"""
        
        # 중복 검증
        if self.duplicate_checker.is_recently_crawled(product_id):
            result = ValidationResult(False, 0.0, [], [])
            result.add_error(f"Product {product_id} was crawled recently (within 10 minutes)")
            return result
        
        # 전체 결과
        overall_result = ValidationResult(True, 1.0, [], [])
        scores = []
        
        # URL 검증
        url_result = self.url_validator.validate_url(url, platform)
        scores.append(url_result.score)
        overall_result.errors.extend(url_result.errors)
        overall_result.warnings.extend(url_result.warnings)
        
        # 상품명 검증
        if 'product_name' in data:
            name_result = self.name_validator.validate_product_name(data['product_name'])
            scores.append(name_result.score)
            overall_result.errors.extend(name_result.errors)
            overall_result.warnings.extend(name_result.warnings)
        
        # 가격 검증
        if 'price' in data and data['price'] is not None:
            price_result = self.price_validator.validate_price(data['price'], platform)
            scores.append(price_result.score)
            overall_result.errors.extend(price_result.errors)
            overall_result.warnings.extend(price_result.warnings)
            
            # 할인율 검증
            discount_result = self.price_validator.validate_discount_rate(
                data.get('discount_rate'),
                data.get('price'),
                data.get('original_price')
            )
            scores.append(discount_result.score)
            overall_result.errors.extend(discount_result.errors)
            overall_result.warnings.extend(discount_result.warnings)
        
        # 재고 상태 검증
        if 'stock_status' in data:
            stock_result = self.stock_validator.validate_stock_status(
                data['stock_status'],
                data.get('stock_quantity')
            )
            scores.append(stock_result.score)
            overall_result.errors.extend(stock_result.errors)
            overall_result.warnings.extend(stock_result.warnings)
        
        # 전체 점수 계산 (가중 평균)
        if scores:
            overall_result.score = sum(scores) / len(scores)
        
        # 에러가 있으면 유효하지 않음
        overall_result.is_valid = len(overall_result.errors) == 0
        
        # 최소 점수 요구사항
        if overall_result.score < 0.3:
            overall_result.add_error("Overall data quality score too low")
        
        return overall_result
    
    def should_save_data(self, validation_result: ValidationResult, min_score: float = 0.7) -> bool:
        """데이터 저장 여부 결정"""
        return validation_result.is_valid and validation_result.score >= min_score
    
    def mark_successful_crawl(self, product_id: str):
        """성공한 크롤링 표시 (중복 방지용)"""
        self.duplicate_checker.mark_as_crawled(product_id)


# 전역 인스턴스
data_validator = DataValidator()


# 편의 함수들
def validate_product_data(data: Dict[str, Any], product_id: str, url: str, platform: PlatformType) -> ValidationResult:
    """상품 데이터 검증 (편의 함수)"""
    return data_validator.validate_crawl_data(data, product_id, url, platform)


def is_data_worth_saving(validation_result: ValidationResult) -> bool:
    """데이터 저장 가치 판단 (편의 함수)"""
    return data_validator.should_save_data(validation_result)


def check_recent_crawl(product_id: str) -> bool:
    """최근 크롤링 확인 (편의 함수)"""
    return data_validator.duplicate_checker.is_recently_crawled(product_id)