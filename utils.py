"""
네이버 뉴스 크롤러 유틸리티 함수들
"""

import json
import logging
import os
import csv
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """
    설정 파일을 로드합니다.
    
    Args:
        config_path: 설정 파일 경로
        
    Returns:
        설정 딕셔너리
        
    Raises:
        FileNotFoundError: 설정 파일이 없는 경우
        json.JSONDecodeError: JSON 형식이 잘못된 경우
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logging.info(f"설정 파일 로드 완료: {config_path}")
        return config
    except FileNotFoundError:
        logging.error(f"설정 파일을 찾을 수 없습니다: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"설정 파일 JSON 형식 오류: {e}")
        raise


def load_urls(url_file: str) -> List[str]:
    """
    URL 목록 파일을 로드합니다.
    
    Args:
        url_file: URL 목록 파일 경로
        
    Returns:
        URL 리스트 (주석 및 빈 줄 제외)
    """
    urls = []
    try:
        with open(url_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # 빈 줄이나 주석(#으로 시작) 스킵
                if line and not line.startswith('#'):
                    if line.startswith('http'):
                        urls.append(line)
                    else:
                        logging.warning(f"잘못된 URL 형식 (라인 {line_num}): {line}")
        
        logging.info(f"URL {len(urls)}개 로드 완료")
        return urls
    except FileNotFoundError:
        logging.error(f"URL 파일을 찾을 수 없습니다: {url_file}")
        raise


def setup_logger(config: Dict[str, Any]) -> logging.Logger:
    """
    로깅을 설정합니다.
    
    Args:
        config: 설정 딕셔너리
        
    Returns:
        설정된 로거
    """
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO'))
    log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_file = log_config.get('file', 'scraper.log')
    
    # 로거 설정
    logger = logging.getLogger('naver_scraper')
    logger.setLevel(log_level)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 파일 핸들러
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(log_format)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    logger.info("로깅 설정 완료")
    return logger


def create_output_directory(output_dir: str) -> str:
    """
    출력 디렉토리를 생성합니다.
    
    Args:
        output_dir: 출력 디렉토리 경로
        
    Returns:
        생성된 디렉토리 경로
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    logging.info(f"출력 디렉토리 준비: {output_dir}")
    return output_dir


def generate_output_filename(config: Dict[str, Any], output_dir: str) -> str:
    """
    출력 파일명을 생성합니다.
    
    Args:
        config: 설정 딕셔너리
        output_dir: 출력 디렉토리
        
    Returns:
        완전한 파일 경로
    """
    output_config = config.get('output', {})
    prefix = output_config.get('filename_prefix', 'naver_news')
    file_format = output_config.get('format', 'csv')
    include_timestamp = output_config.get('include_timestamp', True)
    
    if include_timestamp:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{prefix}_{timestamp}.{file_format}"
    else:
        filename = f"{prefix}.{file_format}"
    
    return os.path.join(output_dir, filename)


def save_results(data: List[Dict[str, Any]], config: Dict[str, Any], output_path: str) -> None:
    """
    크롤링 결과를 파일로 저장합니다.
    
    Args:
        data: 크롤링된 데이터 리스트
        config: 설정 딕셔너리
        output_path: 출력 파일 경로
    """
    if not data:
        logging.warning("저장할 데이터가 없습니다")
        return
    
    output_config = config.get('output', {})
    file_format = output_config.get('format', 'csv').lower()
    
    try:
        if file_format == 'csv':
            _save_as_csv(data, output_path)
        elif file_format == 'json':
            _save_as_json(data, output_path)
        elif file_format == 'excel':
            _save_as_excel(data, output_path)
        else:
            logging.error(f"지원하지 않는 파일 형식: {file_format}")
            return
        
        logging.info(f"결과 저장 완료: {output_path} ({len(data)}개 항목)")
    except Exception as e:
        logging.error(f"파일 저장 실패: {e}")
        raise


def _save_as_csv(data: List[Dict[str, Any]], output_path: str) -> None:
    """CSV 형식으로 저장"""
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')


def _save_as_json(data: List[Dict[str, Any]], output_path: str) -> None:
    """JSON 형식으로 저장"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _save_as_excel(data: List[Dict[str, Any]], output_path: str) -> None:
    """Excel 형식으로 저장"""
    df = pd.DataFrame(data)
    df.to_excel(output_path, index=False, engine='openpyxl')


def save_failed_urls(failed_urls: List[str], output_dir: str) -> None:
    """
    실패한 URL들을 별도 파일로 저장합니다.
    
    Args:
        failed_urls: 실패한 URL 리스트
        output_dir: 출력 디렉토리
    """
    if not failed_urls:
        return
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    failed_file = os.path.join(output_dir, f"failed_urls_{timestamp}.txt")
    
    try:
        with open(failed_file, 'w', encoding='utf-8') as f:
            f.write("# 크롤링 실패한 URL 목록\n")
            f.write(f"# 생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for url in failed_urls:
                f.write(f"{url}\n")
        
        logging.info(f"실패한 URL 저장: {failed_file} ({len(failed_urls)}개)")
    except Exception as e:
        logging.error(f"실패한 URL 저장 실패: {e}")


def validate_config(config: Dict[str, Any]) -> bool:
    """
    설정 파일의 유효성을 검사합니다.
    
    Args:
        config: 설정 딕셔너리
        
    Returns:
        유효성 검사 결과
    """
    required_sections = ['scraping', 'selenium', 'output', 'naver_selectors']
    
    for section in required_sections:
        if section not in config:
            logging.error(f"필수 설정 섹션이 없습니다: {section}")
            return False
    
    # scraping 섹션 검증
    scraping = config['scraping']
    if scraping.get('delay_between_requests', 0) < 0:
        logging.error("delay_between_requests는 0 이상이어야 합니다")
        return False
    
    if scraping.get('max_workers', 1) < 1:
        logging.error("max_workers는 1 이상이어야 합니다")
        return False
    
    # output 섹션 검증
    output = config['output']
    supported_formats = ['csv', 'json', 'excel']
    if output.get('format', 'csv') not in supported_formats:
        logging.error(f"지원하지 않는 출력 형식입니다. 지원 형식: {supported_formats}")
        return False
    
    logging.info("설정 파일 유효성 검사 통과")
    return True


def get_system_info() -> Dict[str, Any]:
    """
    시스템 정보를 반환합니다.
    
    Returns:
        시스템 정보 딕셔너리
    """
    import psutil
    import platform
    
    return {
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'cpu_count': psutil.cpu_count(),
        'memory_total': psutil.virtual_memory().total,
        'memory_available': psutil.virtual_memory().available,
    }