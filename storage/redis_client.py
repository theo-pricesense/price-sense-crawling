"""
Redis connection and queue management for Price Sense crawler system.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager, contextmanager

import redis
from redis import ConnectionPool, Redis
from redis.exceptions import ConnectionError, TimeoutError, RedisError

from config.settings import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Redis 연결 및 큐 관리자"""
    
    def __init__(self):
        self._pool: ConnectionPool = None
        self._client: Redis = None
        self._initialized = False
    
    def initialize(self) -> None:
        """Redis 연결 초기화"""
        if self._initialized:
            return
            
        try:
            # 연결 풀 생성
            self._pool = ConnectionPool.from_url(
                settings.redis.url,
                max_connections=settings.redis.max_connections,
                socket_timeout=settings.redis.socket_timeout,
                socket_connect_timeout=settings.redis.socket_connect_timeout,
                retry_on_timeout=settings.redis.retry_on_timeout,
                health_check_interval=settings.redis.health_check_interval,
                decode_responses=True
            )
            
            # Redis 클라이언트 생성
            self._client = Redis(connection_pool=self._pool)
            
            # 연결 테스트
            self._client.ping()
            
            self._initialized = True
            logger.info("Redis connection initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis connection: {e}")
            raise
    
    @contextmanager
    def get_client(self):
        """Redis 클라이언트 컨텍스트 매니저"""
        if not self._initialized:
            self.initialize()
            
        try:
            yield self._client
        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Redis connection error: {e}")
            raise
        except RedisError as e:
            logger.error(f"Redis operation error: {e}")
            raise
    
    def check_connection(self) -> bool:
        """Redis 연결 상태 확인"""
        try:
            with self.get_client() as client:
                client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis connection check failed: {e}")
            return False
    
    def close(self) -> None:
        """Redis 연결 종료"""
        if self._client:
            self._client.connection_pool.disconnect()
            logger.info("Redis connection closed")
        self._initialized = False


class TaskQueue:
    """크롤링 작업 큐 관리"""
    
    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
        self.crawl_queue = settings.redis.crawl_queue_name
        self.result_queue = settings.redis.result_queue_name
        self.dead_letter_queue = settings.redis.dead_letter_queue
    
    def push_task(self, task_data: Dict[str, Any], priority: str = "normal") -> bool:
        """크롤링 작업을 큐에 추가"""
        try:
            with self.redis_manager.get_client() as client:
                # 작업 데이터에 메타데이터 추가
                task_data.update({
                    "created_at": datetime.utcnow().isoformat(),
                    "priority": priority,
                    "retry_count": task_data.get("retry_count", 0)
                })
                
                task_json = json.dumps(task_data, ensure_ascii=False)
                
                # 우선순위에 따라 큐 선택
                queue_name = f"{self.crawl_queue}:{priority}"
                
                # LPUSH로 큐에 추가 (LIFO)
                client.lpush(queue_name, task_json)
                
                logger.info(f"Task added to queue: {task_data.get('task_id', 'unknown')}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to push task to queue: {e}")
            return False
    
    def pop_task(self, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """큐에서 작업을 가져옴 (블로킹)"""
        try:
            with self.redis_manager.get_client() as client:
                # 높은 우선순위부터 확인
                queue_names = [
                    f"{self.crawl_queue}:high",
                    f"{self.crawl_queue}:normal"
                ]
                
                # BRPOP으로 블로킹 팝 (FIFO)
                result = client.brpop(queue_names, timeout=timeout)
                
                if result:
                    queue_name, task_json = result
                    task_data = json.loads(task_json)
                    logger.debug(f"Task popped from queue: {task_data.get('task_id', 'unknown')}")
                    return task_data
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to pop task from queue: {e}")
            return None
    
    def push_result(self, result_data: Dict[str, Any]) -> bool:
        """크롤링 결과를 결과 큐에 추가"""
        try:
            with self.redis_manager.get_client() as client:
                result_data["completed_at"] = datetime.utcnow().isoformat()
                result_json = json.dumps(result_data, ensure_ascii=False)
                
                client.lpush(self.result_queue, result_json)
                
                logger.info(f"Result added to queue: {result_data.get('task_id', 'unknown')}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to push result to queue: {e}")
            return False
    
    def push_failed_task(self, task_data: Dict[str, Any], error: str) -> bool:
        """실패한 작업을 재시도하거나 데드레터 큐로 이동"""
        try:
            retry_count = task_data.get("retry_count", 0)
            max_retries = settings.crawler.max_retries
            
            if retry_count < max_retries:
                # 재시도
                task_data["retry_count"] = retry_count + 1
                task_data["last_error"] = error
                task_data["retry_at"] = datetime.utcnow().isoformat()
                
                return self.push_task(task_data, task_data.get("priority", "normal"))
            else:
                # 데드레터 큐로 이동
                with self.redis_manager.get_client() as client:
                    task_data.update({
                        "final_error": error,
                        "failed_at": datetime.utcnow().isoformat(),
                        "retry_count": retry_count
                    })
                    
                    failed_json = json.dumps(task_data, ensure_ascii=False)
                    client.lpush(self.dead_letter_queue, failed_json)
                    
                    logger.warning(f"Task moved to dead letter queue: {task_data.get('task_id', 'unknown')}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to handle failed task: {e}")
            return False
    
    def get_queue_stats(self) -> Dict[str, int]:
        """큐 통계 정보 조회"""
        try:
            with self.redis_manager.get_client() as client:
                stats = {
                    "crawl_high": client.llen(f"{self.crawl_queue}:high"),
                    "crawl_normal": client.llen(f"{self.crawl_queue}:normal"),
                    "result": client.llen(self.result_queue),
                    "dead_letter": client.llen(self.dead_letter_queue)
                }
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {}
    
    def clear_queue(self, queue_type: str) -> bool:
        """큐 초기화 (개발/테스트용)"""
        try:
            with self.redis_manager.get_client() as client:
                if queue_type == "crawl":
                    client.delete(f"{self.crawl_queue}:high")
                    client.delete(f"{self.crawl_queue}:normal")
                elif queue_type == "result":
                    client.delete(self.result_queue)
                elif queue_type == "dead_letter":
                    client.delete(self.dead_letter_queue)
                elif queue_type == "all":
                    client.delete(f"{self.crawl_queue}:high")
                    client.delete(f"{self.crawl_queue}:normal")
                    client.delete(self.result_queue)
                    client.delete(self.dead_letter_queue)
                
                logger.info(f"Queue cleared: {queue_type}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear queue: {e}")
            return False


class CacheManager:
    """Redis 기반 캐시 관리"""
    
    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
        self.default_ttl = 3600  # 1시간
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """캐시 값 설정"""
        try:
            with self.redis_manager.get_client() as client:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                
                ttl = ttl or self.default_ttl
                client.setex(key, ttl, value)
                return True
                
        except Exception as e:
            logger.error(f"Failed to set cache: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """캐시 값 조회"""
        try:
            with self.redis_manager.get_client() as client:
                value = client.get(key)
                if value is None:
                    return None
                
                # JSON 파싱 시도
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
                    
        except Exception as e:
            logger.error(f"Failed to get cache: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """캐시 삭제"""
        try:
            with self.redis_manager.get_client() as client:
                result = client.delete(key)
                return result > 0
                
        except Exception as e:
            logger.error(f"Failed to delete cache: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """캐시 존재 여부 확인"""
        try:
            with self.redis_manager.get_client() as client:
                return client.exists(key) > 0
                
        except Exception as e:
            logger.error(f"Failed to check cache existence: {e}")
            return False


# 전역 인스턴스
redis_manager = RedisManager()
task_queue = TaskQueue(redis_manager)
cache_manager = CacheManager(redis_manager)


# 편의 함수들
def init_redis() -> None:
    """Redis 연결 초기화"""
    redis_manager.initialize()


def close_redis() -> None:
    """Redis 연결 종료"""
    redis_manager.close()