#!/usr/bin/env python3
"""
배치 스크래퍼 - 복수의 URL 파일들을 순차적으로 처리
"""

import argparse
import os
import sys
import subprocess
import time
from pathlib import Path
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class BatchResult:
    """배치 처리 결과"""
    total_files: int
    success_count: int
    fail_count: int
    total_time: float
    failed_files: List[str]
    start_time: datetime
    end_time: datetime


class BatchScraper:
    """복수의 URL 파일들을 순차적으로 처리하는 배치 스크래퍼"""

    def __init__(self, scraper_path: str = 'main_scraper.py', delay: int = 5):
        """
        배치 스크래퍼 초기화

        Args:
            scraper_path: 메인 스크래퍼 파일 경로
            delay: 파일 간 처리 대기 시간(초)
        """
        self.scraper_path = scraper_path
        self.delay = delay
        self.continue_on_error = False
        self.logger = self._setup_logger()

        # 처리 상태 추적
        self.current_file_index = 0
        self.total_files = 0
        self.processed_files = []
        self.failed_files = []

    def _setup_logger(self) -> logging.Logger:
        """로거 설정"""
        try:
            from utils import setup_logger

            config = {
                'logging': {
                    'level': 'INFO',
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    'console_format':'%(asctime)s - %(levelname)s - [BATCH RUNNER] - %(message)s',
                    'file': 'logs/batch_scraper.log'
                }
            }
            logger = setup_logger(config)
            logger.name = 'batch_scraper_runner'
            return logger

        except ImportError:
            # fallback 로깅 설정
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('batch_scraper.log', encoding='utf-8'),
                    logging.StreamHandler(sys.stdout)
                ]
            )
            return logging.getLogger('batch_scraper')

    def validate_scraper(self) -> bool:
        """메인 스크래퍼 파일 존재 확인"""
        if not os.path.exists(self.scraper_path):
            self.logger.error(f"메인 스크래퍼 파일을 찾을 수 없습니다: {self.scraper_path}")
            return False
        return True

    def find_url_files(self, directory: str = '.', pattern: str = '*.txt') -> List[str]:
        """
        URL 파일들 찾기

        Args:
            directory: 검색할 디렉토리
            pattern: 파일 패턴

        Returns:
            찾은 파일들의 경로 리스트
        """
        path = Path(directory)
        url_files = list(path.glob(pattern))
        return sorted([str(f) for f in url_files])

    def validate_files(self, files: List[str]) -> List[str]:
        """
        파일 존재 여부 확인

        Args:
            files: 확인할 파일 경로 리스트

        Returns:
            존재하는 파일들의 리스트
        """
        valid_files = []
        for file in files:
            if os.path.exists(file):
                valid_files.append(file)
            else:
                self.logger.warning(f"파일을 찾을 수 없습니다: {file}")
        return valid_files

    def run_single_scraper(self, url_file: str, should_upload: bool = False) -> bool:
        """
        개별 스크래퍼 실행

        Args:
            url_file: 처리할 URL 파일

        Returns:
            성공 여부
        """
        try:
            self.logger.info(f"스크래핑 시작: {url_file}")

            self.logger.info(f"구글드라이브 업로드: {should_upload}")

            # 구글 드라이브 업로드 설정
            if should_upload:
                cmd.append('--upload')

            python_exe = sys.executable  # 현재 파이썬 실행 파일 경로

            if os.name == 'nt':  # Windows
                # 가상환경이 활성화되어 있는지 확인
                if 'VIRTUAL_ENV' in os.environ:
                    venv_python = os.path.join(
                        os.environ['VIRTUAL_ENV'], 'Scripts', 'python.exe')
                    if os.path.exists(venv_python):
                        python_exe = venv_python

            cmd = [python_exe, self.scraper_path, '--urls', url_file]

            result = subprocess.run(
                cmd,
                capture_output=False,
                text=True,
                timeout=18000  # 1시간 타임아웃
            )

            if result.returncode == 0:
                self.logger.info(f"스크래핑 완료: {url_file}")
                return True
            else:
                self.logger.error(f"스크래핑 실패: {url_file}")
                if result.stderr:
                    self.logger.error(f"Error: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error(f"스크래핑 타임아웃: {url_file}")
            return False
        except Exception as e:
            self.logger.error(f"스크래핑 오류: {url_file} - {str(e)}")
            return False

    def log_progress(self):
        """진행률 로깅"""
        progress = (self.current_file_index / self.total_files) * 100
        self.logger.info(
            f"진행률: {self.current_file_index}/{self.total_files} ({progress:.1f}%)")

    def wait_between_files(self):
        """파일 간 대기"""
        if self.current_file_index < self.total_files:
            self.logger.info(f"{self.delay}초 대기 중...")
            time.sleep(self.delay)

    def process_files(self, 
                      files: List[str], 
                      continue_on_error: bool = False,
                      should_upload: bool = False) -> BatchResult:
        """
        파일들을 배치 처리

        Args:
            files: 처리할 파일 리스트
            continue_on_error: 오류 발생 시 계속 진행 여부

        Returns:
            배치 처리 결과
        """
        self.continue_on_error = continue_on_error
        self.total_files = len(files)
        self.current_file_index = 0
        self.processed_files = []
        self.failed_files = []

        start_time = datetime.now()
        self.logger.info(f"배치 처리 시작 - 총 {self.total_files}개 파일")
        self.logger.info(f"처리할 파일들: {files}")

        success_count = 0
        fail_count = 0

        for file in files:
            self.current_file_index += 1
            self.log_progress()
            self.logger.info(f"처리 중: {file}")

            success = self.run_single_scraper(file, should_upload)

            if success:
                success_count += 1
                self.processed_files.append(file)
            else:
                fail_count += 1
                self.failed_files.append(file)

                if not self.continue_on_error:
                    self.logger.error("오류로 인해 배치 처리를 중단합니다.")
                    self.logger.error(
                        "--continue-on-error 옵션을 사용하면 계속 진행할 수 있습니다.")
                    break

            # 마지막 파일이 아니면 대기
            if self.current_file_index < self.total_files:
                self.wait_between_files()

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        result = BatchResult(
            total_files=self.total_files,
            success_count=success_count,
            fail_count=fail_count,
            total_time=total_time,
            failed_files=self.failed_files,
            start_time=start_time,
            end_time=end_time
        )

        self._log_summary(result)
        return result

    def _log_summary(self, result: BatchResult):
        """처리 결과 요약 로깅"""
        self.logger.info("=" * 50)
        self.logger.info("배치 처리 완료")
        self.logger.info(
            f"처리 시간: {result.start_time.strftime('%Y-%m-%d %H:%M:%S')} ~ {result.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"총 처리 시간: {result.total_time:.2f}초")
        self.logger.info(f"성공: {result.success_count}개")
        self.logger.info(f"실패: {result.fail_count}개")
        self.logger.info(f"총 파일: {result.total_files}개")

        if result.failed_files:
            self.logger.warning(f"실패한 파일들: {result.failed_files}")

    def run_batch(self, 
                  files: Optional[List[str]] = None,
                  directory: str = '.', 
                  pattern: str = 'url*.txt',
                  continue_on_error: bool = False,
                  should_upload: bool = False) -> BatchResult:
        """
        배치 실행 (메인 인터페이스)

        Args:
            files: 처리할 파일 리스트 (None이면 패턴으로 검색)
            directory: 파일 검색 디렉토리
            pattern: 파일 검색 패턴
            continue_on_error: 오류 발생 시 계속 진행 여부

        Returns:
            배치 처리 결과
        """
        # 스크래퍼 검증
        if not self.validate_scraper():
            raise FileNotFoundError(f"스크래퍼 파일을 찾을 수 없습니다: {self.scraper_path}")

        # 파일 수집
        if files:
            url_files = files
        else:
            url_files = self.find_url_files(directory, pattern)

        if not url_files:
            raise ValueError("처리할 URL 파일을 찾을 수 없습니다.")

        # 파일 검증
        valid_files = self.validate_files(url_files)
        if not valid_files:
            raise ValueError("유효한 URL 파일이 없습니다.")

        # 배치 처리 실행
        return self.process_files(valid_files, continue_on_error, should_upload)


def main():
    """CLI 진입점"""
    parser = argparse.ArgumentParser(
        description='복수의 URL 파일을 순차적으로 처리하는 배치 스크래퍼')

    # 파일 지정 옵션
    parser.add_argument('--files', nargs='+',
                        help='처리할 URL 파일들 (예: url1.txt url2.txt url3.txt)')
    parser.add_argument('--directory', '-d', default='.',
                        help='URL 파일들이 있는 디렉토리 (기본값: 현재 디렉토리)')
    parser.add_argument('--pattern', '-p', default='url*.txt',
                        help='URL 파일 패턴 (기본값: url*.txt)')

    # 실행 옵션
    parser.add_argument('--scraper', default='main_scraper.py',
                        help='메인 스크래퍼 파일 경로 (기본값: main_scraper.py)')
    parser.add_argument('--delay', type=int, default=5,
                        help='파일 간 처리 대기 시간(초) (기본값: 5)')
    parser.add_argument('--continue-on-error',
                        action='store_true', help='오류 발생 시에도 계속 진행')
    
    # 드라이브 업로드 옵션
    parser.add_argument('--upload',
                        action='store_true', 
                        help='구글 드라이브에 작업내용 업로드')

    args = parser.parse_args()

    try:
        # 배치 스크래퍼 인스턴스 생성
        batch_scraper = BatchScraper(
            scraper_path=args.scraper,
            delay=args.delay
        )

        # 배치 실행
        result = batch_scraper.run_batch(
            files=args.files,
            directory=args.directory,
            pattern=args.pattern,
            continue_on_error=args.continue_on_error,
            should_upload=args.upload
        )

        # 실패한 파일이 있으면 종료 코드 1로 종료
        if result.fail_count > 0:
            sys.exit(1)

    except Exception as e:
        print(f"배치 처리 중 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
