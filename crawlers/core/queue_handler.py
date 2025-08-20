"""
Redis queue handler for processing crawling tasks.

This module handles the communication between the NestJS server and Python crawler
via Redis queues, processing crawling tasks and sending back results.
"""

import asyncio
import json
import signal
import time
from datetime import datetime
from typing import Dict, Any, Optional, Type
from contextlib import asynccontextmanager

from crawlers.core.base_crawler import BaseCrawler
from crawlers.platforms.coupang import CoupangCrawler
from crawlers.platforms.naver_shopping import NaverShoppingCrawler
from crawlers.platforms.smartstore import SmartStoreCrawler
from models.base import PlatformType
from storage.redis_client import task_queue, redis_manager
from utils.logging import get_logger


class CrawlTask:
    """크롤링 작업을 나타내는 데이터 클래스"""
    
    def __init__(self, data: Dict[str, Any]):
        self.task_id = data.get('task_id')
        self.product_id = str(data.get('product_id'))
        self.url = data.get('url')
        self.platform = PlatformType(data.get('platform'))
        self.priority = data.get('priority', 'normal')
        self.retry_count = data.get('retry_count', 0)
        self.user_id = data.get('user_id')
        self.created_at = data.get('created_at')
        self.raw_data = data
    
    def __repr__(self):
        return f"CrawlTask(id={self.task_id}, product={self.product_id}, platform={self.platform.value})"


class QueueHandler:
    """Redis 큐 처리 핸들러"""
    
    def __init__(self):
        self.logger = get_logger("queue_handler")
        self.running = False
        self.crawler_instances = {}
        
        # 플랫폼별 크롤러 클래스 매핑
        self.crawler_classes: Dict[PlatformType, Type[BaseCrawler]] = {
            PlatformType.COUPANG: CoupangCrawler,
            PlatformType.NAVER_SHOPPING: NaverShoppingCrawler,
            PlatformType.SMART_STORE: SmartStoreCrawler,
        }
        
        # 성능 메트릭
        self.stats = {
            'processed_tasks': 0,
            'successful_tasks': 0,
            'failed_tasks': 0,
            'start_time': time.time()
        }
        
        # Graceful shutdown을 위한 시그널 핸들러
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러 - Graceful shutdown"""
        self.logger.info(f"Received signal {signum}, initiating shutdown...")
        self.running = False
    
    async def start(self, worker_id: str = "worker-1"):
        """큐 처리 시작"""
        self.running = True
        self.worker_id = worker_id
        
        self.logger.info(f"Queue handler started (worker_id: {worker_id})")
        self.logger.info(f"Supported platforms: {list(self.crawler_classes.keys())}")
        
        try:
            # Redis 연결 초기화
            redis_manager.initialize()
            
            # 메인 처리 루프
            await self._process_loop()
            
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        except Exception as e:
            self.logger.error(f"Error in queue handler: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _process_loop(self):
        """메인 처리 루프"""
        consecutive_empty_polls = 0
        max_empty_polls = 6  # 1분간 작업이 없으면 잠시 대기
        
        while self.running:
            try:
                # 큐에서 작업 가져오기 (10초 블로킹)
                task_data = task_queue.pop_task(timeout=10)
                
                if task_data:
                    consecutive_empty_polls = 0
                    await self._process_task(task_data)
                else:
                    consecutive_empty_polls += 1
                    
                    # 연속으로 빈 큐를 여러 번 확인하면 잠시 대기
                    if consecutive_empty_polls >= max_empty_polls:
                        self.logger.debug("No tasks for a while, sleeping...")
                        await asyncio.sleep(10)
                        consecutive_empty_polls = 0
                
            except Exception as e:
                self.logger.error(f"Error in process loop: {e}")
                await asyncio.sleep(5)  # 에러 발생시 잠시 대기
        
        self.logger.info("Process loop ended")
    
    async def _process_task(self, task_data: Dict[str, Any]):
        """개별 작업 처리"""
        task = None
        start_time = time.time()
        
        try:
            # 작업 객체 생성
            task = CrawlTask(task_data)
            self.logger.info(f"Processing task: {task}")
            
            # 플랫폼별 크롤러 선택
            crawler_class = self.crawler_classes.get(task.platform)
            if not crawler_class:
                raise ValueError(f"Unsupported platform: {task.platform.value}")
            
            # 크롤러 인스턴스 가져오기 또는 생성
            crawler = await self._get_crawler_instance(task.platform, crawler_class)
            
            # 크롤링 실행
            result = await crawler.scrape_product(task.product_id, task.url)
            
            # 결과 처리
            await self._handle_result(task, result, time.time() - start_time)
            
            self.stats['processed_tasks'] += 1
            if result.success:
                self.stats['successful_tasks'] += 1
            else:
                self.stats['failed_tasks'] += 1
                
        except Exception as e:
            self.logger.error(f"Error processing task {task}: {e}")
            
            if task:
                # 실패한 작업 처리
                await self._handle_task_failure(task, str(e))
                self.stats['failed_tasks'] += 1
            
            self.stats['processed_tasks'] += 1
    
    async def _get_crawler_instance(self, platform: PlatformType, crawler_class: Type[BaseCrawler]) -> BaseCrawler:
        """크롤러 인스턴스 관리 (재사용을 위해 캐시)"""
        
        if platform not in self.crawler_instances:
            # 새 크롤러 인스턴스 생성
            crawler = crawler_class(
                headless=True,
                request_delay=2.0,
                timeout=30,
                max_retries=2  # 큐 레벨에서도 재시도하므로 크롤러 레벨은 줄임
            )
            
            # 비동기 초기화
            await crawler.initialize()
            
            self.crawler_instances[platform] = crawler
            self.logger.info(f"Created new crawler instance for {platform.value}")
        
        return self.crawler_instances[platform]
    
    async def _handle_result(self, task: CrawlTask, result, execution_time: float):
        """크롤링 결과 처리"""
        
        try:
            if result.success:
                # 성공 결과를 Redis 결과 큐에 전송
                result_data = {
                    "task_id": task.task_id,
                    "status": "success",
                    "data": {
                        "product_name": result.product_name,
                        "price": float(result.price) if result.price else None,
                        "original_price": float(result.original_price) if result.original_price else None,
                        "discount_rate": result.discount_rate,
                        "stock_status": result.stock_status.value,
                        "stock_quantity": result.stock_quantity,
                        "promotion_info": result.promotion_info,
                        "confidence_score": result.confidence_score,
                        "image_url": result.image_url,
                        "category": result.category,
                        "brand": result.brand,
                        "rating": result.rating,
                        "review_count": result.review_count
                    },
                    "execution_time": int(execution_time * 1000),  # 밀리초로 변환
                    "worker_id": self.worker_id,
                    "platform": task.platform.value
                }
                
                success = task_queue.push_result(result_data)
                
                if success:
                    self.logger.info(f"Task {task.task_id} completed successfully")
                else:
                    self.logger.error(f"Failed to send result for task {task.task_id}")
                    
            else:
                # 실패한 작업 처리
                await self._handle_task_failure(task, result.error_message)
                
        except Exception as e:
            self.logger.error(f"Error handling result for task {task.task_id}: {e}")
            await self._handle_task_failure(task, f"Result handling error: {str(e)}")
    
    async def _handle_task_failure(self, task: CrawlTask, error_message: str):
        """실패한 작업 처리"""
        
        try:
            # 재시도하거나 데드레터 큐로 이동
            success = task_queue.push_failed_task(task.raw_data, error_message)
            
            if success:
                if task.retry_count < 3:  # 설정에서 가져와야 함
                    self.logger.warning(f"Task {task.task_id} failed, will retry (attempt {task.retry_count + 1})")
                else:
                    self.logger.error(f"Task {task.task_id} permanently failed: {error_message}")
            else:
                self.logger.error(f"Failed to handle task failure for {task.task_id}")
            
            # 실패 결과도 결과 큐에 전송
            failure_result = {
                "task_id": task.task_id,
                "status": "failed",
                "error": error_message,
                "error_code": "CRAWLING_FAILED",
                "retry_count": task.retry_count,
                "worker_id": self.worker_id,
                "platform": task.platform.value
            }
            
            task_queue.push_result(failure_result)
            
        except Exception as e:
            self.logger.error(f"Error in task failure handler: {e}")
    
    async def _cleanup(self):
        """리소스 정리"""
        self.logger.info("Starting cleanup...")
        
        try:
            # 모든 크롤러 인스턴스 정리
            for platform, crawler in self.crawler_instances.items():
                try:
                    await crawler.cleanup()
                    self.logger.debug(f"Cleaned up crawler for {platform.value}")
                except Exception as e:
                    self.logger.error(f"Error cleaning up crawler for {platform.value}: {e}")
            
            self.crawler_instances.clear()
            
            # Redis 연결 정리
            redis_manager.close()
            
            # 통계 출력
            self._log_final_stats()
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
        
        self.logger.info("Cleanup completed")
    
    def _log_final_stats(self):
        """최종 통계 로깅"""
        runtime = time.time() - self.stats['start_time']
        
        self.logger.info("=== Final Statistics ===")
        self.logger.info(f"Runtime: {runtime:.1f} seconds")
        self.logger.info(f"Total tasks processed: {self.stats['processed_tasks']}")
        self.logger.info(f"Successful tasks: {self.stats['successful_tasks']}")
        self.logger.info(f"Failed tasks: {self.stats['failed_tasks']}")
        
        if self.stats['processed_tasks'] > 0:
            success_rate = (self.stats['successful_tasks'] / self.stats['processed_tasks']) * 100
            avg_time = runtime / self.stats['processed_tasks']
            self.logger.info(f"Success rate: {success_rate:.1f}%")
            self.logger.info(f"Average time per task: {avg_time:.1f} seconds")
    
    def get_stats(self) -> Dict[str, Any]:
        """현재 통계 반환"""
        runtime = time.time() - self.stats['start_time']
        
        return {
            **self.stats,
            'runtime': runtime,
            'success_rate': (self.stats['successful_tasks'] / max(1, self.stats['processed_tasks'])) * 100,
            'worker_id': self.worker_id,
            'running': self.running
        }


# 편의 함수
async def run_queue_handler(worker_id: str = "worker-1"):
    """큐 핸들러 실행"""
    handler = QueueHandler()
    await handler.start(worker_id)


# CLI에서 직접 실행할 수 있도록
if __name__ == "__main__":
    import sys
    
    worker_id = sys.argv[1] if len(sys.argv) > 1 else "worker-1"
    
    try:
        asyncio.run(run_queue_handler(worker_id))
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)