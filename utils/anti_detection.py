"""
Anti-detection utilities for web crawling.

This module provides various techniques to avoid detection by e-commerce sites,
including user-agent rotation, request delays, and browser fingerprint obfuscation.
"""

import asyncio
import random
import time
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from urllib.parse import urlparse

from fake_useragent import UserAgent
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utils.logging import get_logger


@dataclass
class BrowserProfile:
    """브라우저 프로파일 정보"""
    user_agent: str
    screen_resolution: str
    language: str
    timezone: str
    platform: str
    
    
class UserAgentRotator:
    """User-Agent 로테이션 관리"""
    
    def __init__(self, custom_agents: Optional[List[str]] = None):
        self.logger = get_logger("user_agent_rotator")
        self.ua_generator = UserAgent()
        
        # 실제 브라우저 User-Agent 풀
        self.default_agents = [
            # Chrome (Windows)
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            
            # Chrome (macOS)
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            
            # Edge (Windows)
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            
            # Firefox (Windows)
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
            
            # Safari (macOS)
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        ]
        
        # 커스텀 에이전트가 있으면 추가
        if custom_agents:
            self.default_agents.extend(custom_agents)
    
    def get_random_agent(self) -> str:
        """랜덤 User-Agent 반환"""
        try:
            # 80% 확률로 미리 정의된 안전한 User-Agent 사용
            if random.random() < 0.8:
                return random.choice(self.default_agents)
            else:
                # 20% 확률로 fake-useragent 생성기 사용
                return self.ua_generator.random
        except Exception:
            # 에러 발생시 기본값 사용
            return self.default_agents[0]
    
    def get_chrome_agent(self) -> str:
        """Chrome User-Agent 반환"""
        chrome_agents = [ua for ua in self.default_agents if 'Chrome' in ua and 'Edg' not in ua]
        return random.choice(chrome_agents)
    
    def get_mobile_agent(self) -> str:
        """모바일 User-Agent 반환"""
        mobile_agents = [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 14; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
        ]
        return random.choice(mobile_agents)


class BrowserProfileManager:
    """브라우저 프로파일 관리"""
    
    def __init__(self):
        self.logger = get_logger("browser_profile_manager")
        self.ua_rotator = UserAgentRotator()
        
        # 화면 해상도 풀
        self.screen_resolutions = [
            "1920,1080", "1366,768", "1536,864", "1440,900",
            "1600,900", "1280,720", "1680,1050", "2560,1440"
        ]
        
        # 언어 설정
        self.languages = ["ko-KR,ko;q=0.9,en;q=0.8", "ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3"]
        
        # 시간대
        self.timezones = ["Asia/Seoul", "Asia/Tokyo"]
        
        # 플랫폼
        self.platforms = ["Win32", "MacIntel", "Linux x86_64"]
    
    def generate_profile(self, platform_hint: Optional[str] = None) -> BrowserProfile:
        """브라우저 프로파일 생성"""
        
        # 플랫폼 힌트가 있으면 해당 User-Agent 선택
        if platform_hint == "mobile":
            user_agent = self.ua_rotator.get_mobile_agent()
        elif platform_hint == "chrome":
            user_agent = self.ua_rotator.get_chrome_agent()
        else:
            user_agent = self.ua_rotator.get_random_agent()
        
        return BrowserProfile(
            user_agent=user_agent,
            screen_resolution=random.choice(self.screen_resolutions),
            language=random.choice(self.languages),
            timezone=random.choice(self.timezones),
            platform=random.choice(self.platforms)
        )


class RequestDelayManager:
    """요청 지연 관리"""
    
    def __init__(self):
        self.logger = get_logger("request_delay_manager")
        self.last_request_times: Dict[str, float] = {}
        
        # 플랫폼별 최소 지연 시간 (초)
        self.min_delays = {
            "coupang.com": 3.0,
            "shopping.naver.com": 2.0,
            "smartstore.naver.com": 3.5,
            "11st.co.kr": 2.5,
            "default": 2.0
        }
        
        # 플랫폼별 지연 시간 범위
        self.delay_ranges = {
            "coupang.com": (2.0, 5.0),
            "shopping.naver.com": (1.5, 4.0),
            "smartstore.naver.com": (2.5, 6.0),
            "11st.co.kr": (2.0, 4.5),
            "default": (1.5, 4.0)
        }
    
    def get_domain(self, url: str) -> str:
        """URL에서 도메인 추출"""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return "unknown"
    
    async def wait_if_needed(self, url: str, force_delay: bool = False):
        """필요시 대기"""
        domain = self.get_domain(url)
        current_time = time.time()
        
        # 도메인별 마지막 요청 시간 확인
        last_time = self.last_request_times.get(domain, 0)
        
        # 최소 지연 시간 계산
        min_delay = self.min_delays.get(domain, self.min_delays["default"])
        elapsed = current_time - last_time
        
        if elapsed < min_delay or force_delay:
            # 지연 시간 계산 (랜덤 요소 추가)
            delay_range = self.delay_ranges.get(domain, self.delay_ranges["default"])
            delay = random.uniform(*delay_range)
            
            # 이미 경과한 시간 제외
            if not force_delay:
                delay = max(0, min_delay - elapsed + random.uniform(0, 1))
            
            if delay > 0:
                self.logger.debug(f"Waiting {delay:.2f}s before request to {domain}")
                await asyncio.sleep(delay)
        
        # 요청 시간 업데이트
        self.last_request_times[domain] = time.time()
    
    def get_human_like_delay(self, base_delay: float = 2.0) -> float:
        """인간다운 지연 시간 생성"""
        # 기본 지연 + 랜덤 요소 + 가끔 긴 지연 (페이지 읽기 시뮬레이션)
        delay = base_delay
        delay += random.uniform(0.5, 2.0)  # 랜덤 요소
        
        # 5% 확률로 긴 지연 (5-10초)
        if random.random() < 0.05:
            delay += random.uniform(3.0, 8.0)
        
        return delay


class ChromeOptionsEnhancer:
    """Chrome 옵션 강화 (탐지 방지)"""
    
    def __init__(self):
        self.logger = get_logger("chrome_options_enhancer")
    
    def get_stealth_options(self, profile: BrowserProfile, proxy: Optional[str] = None) -> ChromeOptions:
        """탐지 방지 Chrome 옵션"""
        
        options = ChromeOptions()
        
        # 기본 stealth 설정
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-images")  # 이미지 로딩 비활성화로 속도 향상
        
        # User-Agent 설정
        options.add_argument(f"--user-agent={profile.user_agent}")
        
        # 창 크기 설정
        width, height = profile.screen_resolution.split(',')
        options.add_argument(f"--window-size={width},{height}")
        
        # 언어 설정
        options.add_argument(f"--lang={profile.language.split(',')[0]}")
        
        # 자동화 탐지 방지
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Blink 기능 비활성화 (탐지 방지)
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # 기타 탐지 방지 설정
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--disable-ipc-flooding-protection")
        
        # 메모리 최적화
        options.add_argument("--memory-pressure-off")
        options.add_argument("--max_old_space_size=4096")
        
        # 프록시 설정 (옵션)
        if proxy:
            options.add_argument(f"--proxy-server={proxy}")
        
        # Prefs 설정
        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,  # 알림 차단
                "popups": 2,  # 팝업 차단
                "media_stream": 2,  # 미디어 스트림 차단
            },
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 2  # 이미지 차단
        }
        options.add_experimental_option("prefs", prefs)
        
        return options


class AntiDetectionManager:
    """안티 디텍션 총괄 관리자"""
    
    def __init__(self):
        self.logger = get_logger("anti_detection_manager")
        self.profile_manager = BrowserProfileManager()
        self.delay_manager = RequestDelayManager()
        self.options_enhancer = ChromeOptionsEnhancer()
        
        # 현재 세션 정보
        self.current_profiles: Dict[str, BrowserProfile] = {}
        self.session_start_times: Dict[str, float] = {}
    
    def create_session(self, session_id: str, platform_hint: Optional[str] = None) -> BrowserProfile:
        """새 세션 생성"""
        profile = self.profile_manager.generate_profile(platform_hint)
        self.current_profiles[session_id] = profile
        self.session_start_times[session_id] = time.time()
        
        self.logger.info(f"Created session {session_id} with profile: {profile.user_agent[:50]}...")
        return profile
    
    def get_session_profile(self, session_id: str) -> Optional[BrowserProfile]:
        """세션 프로파일 조회"""
        return self.current_profiles.get(session_id)
    
    def get_chrome_options(self, session_id: str, proxy: Optional[str] = None) -> ChromeOptions:
        """세션용 Chrome 옵션 생성"""
        profile = self.current_profiles.get(session_id)
        if not profile:
            profile = self.create_session(session_id)
        
        return self.options_enhancer.get_stealth_options(profile, proxy)
    
    async def wait_before_request(self, url: str, force_delay: bool = False):
        """요청 전 대기"""
        await self.delay_manager.wait_if_needed(url, force_delay)
    
    def should_rotate_session(self, session_id: str, max_session_time: float = 3600) -> bool:
        """세션 로테이션이 필요한지 확인"""
        start_time = self.session_start_times.get(session_id)
        if not start_time:
            return True
        
        elapsed = time.time() - start_time
        return elapsed > max_session_time
    
    def cleanup_session(self, session_id: str):
        """세션 정리"""
        if session_id in self.current_profiles:
            del self.current_profiles[session_id]
        if session_id in self.session_start_times:
            del self.session_start_times[session_id]
        
        self.logger.debug(f"Cleaned up session: {session_id}")
    
    def get_session_stats(self) -> Dict[str, int]:
        """세션 통계"""
        return {
            "active_sessions": len(self.current_profiles),
            "total_requests": len(self.delay_manager.last_request_times)
        }


# 전역 인스턴스
anti_detection_manager = AntiDetectionManager()


# 편의 함수들
def create_stealth_session(session_id: str, platform_hint: Optional[str] = None) -> BrowserProfile:
    """스텔스 세션 생성"""
    return anti_detection_manager.create_session(session_id, platform_hint)


def get_stealth_chrome_options(session_id: str, proxy: Optional[str] = None) -> ChromeOptions:
    """스텔스 Chrome 옵션 생성"""
    return anti_detection_manager.get_chrome_options(session_id, proxy)


async def human_delay(url: str):
    """인간다운 지연 시간 적용"""
    await anti_detection_manager.wait_before_request(url, force_delay=True)