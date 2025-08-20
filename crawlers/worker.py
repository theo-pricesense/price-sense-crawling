"""
Main worker process for Price Sense crawler system.

This is the main entry point for running crawler workers that process
tasks from Redis queues. Supports single worker mode and multi-process mode.
"""

import argparse
import asyncio
import multiprocessing as mp
import os
import signal
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

from crawlers.core.queue_handler import QueueHandler, run_queue_handler
from config.settings import settings
from storage.redis_client import redis_manager, task_queue
from utils.logging import get_logger


class WorkerManager:
    """워커 프로세스들을 관리하는 매니저"""
    
    def __init__(self, num_workers: int = 1, worker_prefix: str = "worker"):
        self.num_workers = num_workers
        self.worker_prefix = worker_prefix
        self.logger = get_logger("worker_manager")
        self.processes: List[mp.Process] = []
        self.running = False
        self.start_time = time.time()
        
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """시그널 핸들러 - Graceful shutdown"""
        self.logger.info(f"Received signal {signum}, shutting down workers...")
        self.running = False
        
    def start(self):
        """워커 프로세스들을 시작"""
        self.running = True
        
        try:
            # Redis 연결 테스트
            self._test_redis_connection()
            
            if self.num_workers == 1:
                # 단일 워커 모드 (현재 프로세스에서 실행)
                self.logger.info("Starting single worker mode")
                self._run_single_worker()
            else:
                # 멀티 프로세스 모드
                self.logger.info(f"Starting {self.num_workers} worker processes")
                self._run_multi_workers()
                
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Error in worker manager: {e}")
            raise
        finally:
            self._cleanup()
    
    def _test_redis_connection(self):
        """Redis 연결 상태 확인"""
        try:
            redis_manager.initialize()
            
            if not redis_manager.check_connection():
                raise ConnectionError("Redis connection failed")
                
            # 큐 상태 확인
            stats = task_queue.get_queue_stats()
            self.logger.info(f"Redis connection OK. Queue stats: {stats}")
            
        except Exception as e:
            self.logger.error(f"Redis connection test failed: {e}")
            raise
    
    def _run_single_worker(self):
        """단일 워커 실행"""
        worker_id = f"{self.worker_prefix}-1"
        
        try:
            # asyncio 이벤트 루프에서 실행
            asyncio.run(run_queue_handler(worker_id))
        except Exception as e:
            self.logger.error(f"Error in single worker: {e}")
            raise
    
    def _run_multi_workers(self):
        """멀티 워커 실행"""
        # 워커 프로세스들 시작
        for i in range(self.num_workers):
            worker_id = f"{self.worker_prefix}-{i+1}"
            
            process = mp.Process(
                target=self._worker_process_target,
                args=(worker_id,),
                name=f"CrawlerWorker-{i+1}"
            )
            
            process.start()
            self.processes.append(process)
            
            self.logger.info(f"Started worker process: {worker_id} (PID: {process.pid})")
        
        # 모든 워커 프로세스 완료 대기
        self._wait_for_workers()
    
    def _worker_process_target(self, worker_id: str):
        """워커 프로세스의 실행 대상"""
        try:
            # 프로세스별 로거 설정
            logger = get_logger(f"worker.{worker_id}")
            logger.info(f"Worker process started: {worker_id} (PID: {os.getpid()})")
            
            # asyncio 이벤트 루프에서 큐 핸들러 실행
            asyncio.run(run_queue_handler(worker_id))
            
        except KeyboardInterrupt:
            pass  # 부모 프로세스에서 처리
        except Exception as e:
            logger = get_logger(f"worker.{worker_id}")
            logger.error(f"Error in worker process {worker_id}: {e}")
            sys.exit(1)
    
    def _wait_for_workers(self):
        """워커 프로세스들의 완료를 대기"""
        while self.running and any(p.is_alive() for p in self.processes):
            # 정기적으로 상태 체크
            alive_workers = [p for p in self.processes if p.is_alive()]
            
            if len(alive_workers) != len(self.processes):
                # 일부 워커가 종료됨
                dead_workers = [p for p in self.processes if not p.is_alive()]
                for worker in dead_workers:
                    self.logger.warning(f"Worker process died: {worker.name} (PID: {worker.pid})")
            
            time.sleep(5)  # 5초마다 체크
        
        self.logger.info("All workers have stopped")
    
    def _cleanup(self):
        """워커 프로세스들 정리"""
        if not self.processes:
            return
        
        self.logger.info("Shutting down worker processes...")
        
        # 모든 프로세스에 SIGTERM 전송
        for process in self.processes:
            if process.is_alive():
                try:
                    process.terminate()
                    self.logger.debug(f"Sent SIGTERM to {process.name}")
                except Exception as e:
                    self.logger.error(f"Error terminating process {process.name}: {e}")
        
        # 프로세스들이 종료되기를 잠시 대기
        time.sleep(2)
        
        # 아직 살아있는 프로세스들을 강제 종료
        for process in self.processes:
            if process.is_alive():
                try:
                    process.kill()
                    self.logger.warning(f"Force killed {process.name}")
                except Exception as e:
                    self.logger.error(f"Error killing process {process.name}: {e}")
        
        # 모든 프로세스 join
        for process in self.processes:
            try:
                process.join(timeout=5)
                if process.is_alive():
                    self.logger.error(f"Process {process.name} did not terminate cleanly")
            except Exception as e:
                self.logger.error(f"Error joining process {process.name}: {e}")
        
        # 실행 통계 출력
        runtime = time.time() - self.start_time
        self.logger.info(f"Worker manager ran for {runtime:.1f} seconds")
        self.logger.info("Worker manager shutdown complete")


class SingleCrawlerTester:
    """개별 크롤러 테스트용 클래스"""
    
    def __init__(self, platform: str):
        self.platform = platform
        self.logger = get_logger("crawler_tester")
    
    async def test_url(self, url: str, product_id: str = "test-product"):
        """특정 URL로 크롤러 테스트"""
        try:
            from models.base import PlatformType
            from crawlers.platforms.coupang import CoupangCrawler
            from crawlers.platforms.naver_shopping import NaverShoppingCrawler
            from crawlers.platforms.smartstore import SmartStoreCrawler
            
            # 플랫폼별 크롤러 매핑
            crawler_classes = {
                'coupang': CoupangCrawler,
                'naver_shopping': NaverShoppingCrawler,
                'smartstore': SmartStoreCrawler,
            }
            
            platform_enum = {
                'coupang': PlatformType.COUPANG,
                'naver_shopping': PlatformType.NAVER_SHOPPING,
                'smartstore': PlatformType.SMART_STORE,
            }
            
            if self.platform not in crawler_classes:
                raise ValueError(f"Unsupported platform: {self.platform}")
            
            crawler_class = crawler_classes[self.platform]
            platform_type = platform_enum[self.platform]
            
            # 크롤러 인스턴스 생성 및 실행
            async with crawler_class(headless=False, request_delay=1.0) as crawler:
                self.logger.info(f"Testing {self.platform} crawler with URL: {url}")
                
                result = await crawler.scrape_product(product_id, url)
                
                # 결과 출력
                self.logger.info("=== Crawling Result ===")
                self.logger.info(f"Success: {result.success}")
                self.logger.info(f"Product Name: {result.product_name}")
                self.logger.info(f"Price: {result.price}")
                self.logger.info(f"Stock Status: {result.stock_status}")
                self.logger.info(f"Confidence Score: {result.confidence_score}")
                
                if not result.success:
                    self.logger.error(f"Error: {result.error_message}")
                
                return result
                
        except Exception as e:
            self.logger.error(f"Test failed: {e}")
            raise


def create_argument_parser():
    """CLI 인자 파서 생성"""
    parser = argparse.ArgumentParser(
        description='Price Sense Crawler Worker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # 단일 워커 실행
  %(prog)s --workers 4              # 4개 워커 프로세스 실행
  %(prog)s --test coupang --url "https://..."  # 쿠팡 크롤러 테스트
        """
    )
    
    parser.add_argument(
        '--workers', '-w',
        type=int,
        default=1,
        help='Number of worker processes (default: 1)'
    )
    
    parser.add_argument(
        '--worker-prefix',
        type=str,
        default='worker',
        help='Worker ID prefix (default: worker)'
    )
    
    parser.add_argument(
        '--test',
        type=str,
        choices=['coupang', 'naver_shopping', 'smartstore'],
        help='Test specific platform crawler'
    )
    
    parser.add_argument(
        '--url',
        type=str,
        help='URL for testing (required with --test)'
    )
    
    parser.add_argument(
        '--product-id',
        type=str,
        default='test-product',
        help='Product ID for testing (default: test-product)'
    )
    
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Log level (default: INFO)'
    )
    
    return parser


def main():
    """메인 함수"""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # 로그 레벨 설정
    import logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    try:
        if args.test:
            # 테스트 모드
            if not args.url:
                parser.error("--url is required when using --test")
            
            tester = SingleCrawlerTester(args.test)
            result = asyncio.run(tester.test_url(args.url, args.product_id))
            
            sys.exit(0 if result.success else 1)
        
        else:
            # 일반 워커 모드
            if args.workers < 1:
                parser.error("Number of workers must be at least 1")
            
            manager = WorkerManager(
                num_workers=args.workers,
                worker_prefix=args.worker_prefix
            )
            
            manager.start()
    
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()