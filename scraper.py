"""
네이버 뉴스 크롤러 메인 모듈
"""

import argparse
import logging
import time
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm
import psutil

from utils import (
    load_config, load_urls, setup_logger, create_output_directory,
    generate_output_filename, save_results, save_failed_urls,
    validate_config, get_system_info
)


class NaverNewsScraper:
    """네이버 뉴스 크롤러 클래스"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        크롤러 초기화
        
        Args:
            config: 설정 딕셔너리
        """
        self.config = config
        self.logger = logging.getLogger('naver_scraper')
        self.scraped_data = []
        self.failed_urls = []
        self.selectors = config['naver_selectors']
        
    def _create_driver(self) -> webdriver.Chrome:
        """Chrome WebDriver 생성"""
        chrome_options = Options()
        
        # 설정에서 Chrome 옵션 추가
        for option in self.config.get('chrome_options', []):
            chrome_options.add_argument(option)
        
        # 헤드리스 모드 설정
        if self.config['scraping'].get('headless', True):
            chrome_options.add_argument('--headless')
        
        # ChromeDriver 서비스 생성
        service = Service(ChromeDriverManager().install())
        
        # WebDriver 생성
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Selenium 설정 적용
        selenium_config = self.config['selenium']
        driver.implicitly_wait(selenium_config.get('implicit_wait', 10))
        driver.set_page_load_timeout(selenium_config.get('page_load_timeout', 30))
        driver.set_script_timeout(selenium_config.get('script_timeout', 30))
        
        # 윈도우 크기 설정
        window_size = selenium_config.get('window_size', {})
        if window_size:
            driver.set_window_size(
                window_size.get('width', 1920),
                window_size.get('height', 1080)
            )
        
        return driver
    
    def _extract_article_data(self, driver: webdriver.Chrome, url: str) -> Optional[Dict[str, Any]]:
        """
        단일 기사에서 데이터 추출
        
        Args:
            driver: WebDriver 인스턴스
            url: 기사 URL
            
        Returns:
            추출된 데이터 딕셔너리 또는 None
        """
        try:
            # 페이지 로드
            driver.get(url)
            
            # 페이지 로드 완료 대기
            WebDriverWait(driver, self.config['selenium']['page_load_timeout']).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 데이터 추출
            article_data = {
                'url': url,
                'scraped_at': datetime.now().isoformat(),
            }
            
            # 제목 추출
            title = self._extract_text_by_selector(driver, self.selectors['title'])
            article_data['title'] = title
            
            # 내용 추출
            content = self._extract_text_by_selector(driver, self.selectors['content'])
            article_data['content'] = content
            
            # 작성자 추출
            author = self._extract_text_by_selector(driver, self.selectors['author'])
            article_data['author'] = author
            
            # 발행일 추출
            publish_date = self._extract_text_by_selector(driver, self.selectors['publish_date'])
            article_data['publish_date'] = publish_date
            
            # 카테고리 추출
            category = self._extract_text_by_selector(driver, self.selectors['category'])
            article_data['category'] = category
            
            # 필수 필드 검증
            if not title or not content:
                self.logger.warning(f"필수 데이터 누락: {url}")
                return None
                
            self.logger.debug(f"데이터 추출 성공: {url}")
            return article_data
            
        except TimeoutException:
            self.logger.error(f"페이지 로드 타임아웃: {url}")
            return None
        except WebDriverException as e:
            self.logger.error(f"WebDriver 오류 ({url}): {e}")
            return None
        except Exception as e:
            self.logger.error(f"예상치 못한 오류 ({url}): {e}")
            return None
    
    def _extract_text_by_selector(self, driver: webdriver.Chrome, selector: str) -> str:
        """
        CSS 선택자로 텍스트 추출
        
        Args:
            driver: WebDriver 인스턴스
            selector: CSS 선택자 (여러 선택자를 콤마로 구분)
            
        Returns:
            추출된 텍스트
        """
        selectors = [s.strip() for s in selector.split(',')]
        
        for sel in selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    # 첫 번째 매칭 요소의 텍스트 반환
                    text = elements[0].get_attribute('textContent') or elements[0].text
                    return text.strip()
            except Exception as e:
                self.logger.debug(f"선택자 '{sel}' 실패: {e}")
                continue
        
        return ""
    
    def _scrape_single_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        단일 URL 크롤링 (스레드 안전)
        
        Args:
            url: 크롤링할 URL
            
        Returns:
            추출된 데이터 또는 None
        """
        driver = None
        try:
            # 각 스레드마다 독립적인 WebDriver 생성
            driver = self._create_driver()
            
            # 데이터 추출
            article_data = self._extract_article_data(driver, url)
            
            # 요청 간 지연
            delay = self.config['scraping'].get('delay_between_requests', 1.0)
            if delay > 0:
                time.sleep(delay)
            
            return article_data
            
        except Exception as e:
            self.logger.error(f"크롤링 실패 ({url}): {e}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def scrape_urls(self, urls: List[str]) -> None:
        """
        URL 목록 크롤링 (순차 처리)
        
        Args:
            urls: 크롤링할 URL 리스트
        """
        retry_count = self.config['scraping'].get('retry_count', 3)
        delay = self.config['scraping'].get('delay_between_requests', 2.0)
        
        self.logger.info(f"크롤링 시작: {len(urls)}개 URL (순차 처리, 요청 간격: {delay}초)")
        
        # 단일 WebDriver 생성
        driver = None
        try:
            driver = self._create_driver()
            self.logger.info("Chrome 브라우저 시작")
            
            # 진행률 표시를 위한 tqdm 설정
            for url in tqdm(urls, desc="크롤링 진행", unit="URL"):
                try:
                    result = self._extract_article_data(driver, url)
                    if result:
                        self.scraped_data.append(result)
                        self.logger.debug(f"성공: {url}")
                    else:
                        self.failed_urls.append(url)
                        self.logger.warning(f"데이터 추출 실패: {url}")
                
                except Exception as e:
                    self.logger.error(f"크롤링 오류 ({url}): {e}")
                    self.failed_urls.append(url)
                
                # 서버 부하 방지를 위한 지연
                if delay > 0:
                    time.sleep(delay)
            
        except Exception as e:
            self.logger.error(f"WebDriver 생성/사용 오류: {e}")
            raise
        finally:
            if driver:
                try:
                    driver.quit()
                    self.logger.info("Chrome 브라우저 종료")
                except:
                    pass
        
        # 재시도 로직
        if self.failed_urls and retry_count > 0:
            self.logger.info(f"실패한 {len(self.failed_urls)}개 URL 재시도 중...")
            self._retry_failed_urls(retry_count)
        
        self.logger.info(f"크롤링 완료: 성공 {len(self.scraped_data)}개, 실패 {len(self.failed_urls)}개")
    
    def _retry_failed_urls(self, retry_count: int) -> None:
        """실패한 URL들 재시도 (순차 처리)"""
        driver = None
        try:
            driver = self._create_driver()
            
            for attempt in range(retry_count):
                if not self.failed_urls:
                    break
                    
                self.logger.info(f"재시도 {attempt + 1}/{retry_count}: {len(self.failed_urls)}개 URL")
                
                current_failed = self.failed_urls.copy()
                self.failed_urls.clear()
                
                for url in tqdm(current_failed, desc=f"재시도 {attempt + 1}", unit="URL"):
                    try:
                        result = self._extract_article_data(driver, url)
                        if result:
                            self.scraped_data.append(result)
                        else:
                            self.failed_urls.append(url)
                    except Exception as e:
                        self.logger.error(f"재시도 오류 ({url}): {e}")
                        self.failed_urls.append(url)
                        
                    # 재시도 시 더 긴 지연
                    retry_delay = self.config['scraping'].get('delay_between_requests', 2.0) * 2
                    time.sleep(retry_delay)
        
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='네이버 뉴스 크롤러')
    parser.add_argument('--urls', required=True, help='URL 목록 파일 경로')
    parser.add_argument('--config', default='config.json', help='설정 파일 경로')
    parser.add_argument('--output', default='output/', help='출력 디렉토리')
    parser.add_argument('--threads', type=int, help='(사용하지 않음 - 순차 처리 모드)')
    
    args = parser.parse_args()

    print("네이버 뉴스 크롤러 시작")
    
    try:
        # 설정 로드 및 검증
        config = load_config(args.config)
        if not validate_config(config):
            sys.exit(1)
        
        # 스레드 수 설정은 더 이상 사용하지 않음 (순차 처리)
        if args.threads:
            logger.warning("--threads 옵션은 순차 처리 모드에서 무시됩니다")
        
        # 로깅 설정
        logger = setup_logger(config)
        
        # 시스템 정보 로그
        system_info = get_system_info()
        logger.info(f"시스템 정보: {system_info}")
        
        # URL 로드
        urls = load_urls(args.urls)
        if not urls:
            logger.error("크롤링할 URL이 없습니다")
            sys.exit(1)
        
        # 출력 디렉토리 생성
        output_dir = create_output_directory(args.output)
        
        # 크롤러 실행
        scraper = NaverNewsScraper(config)
        start_time = datetime.now()
        
        scraper.scrape_urls(urls)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        # 결과 저장
        if scraper.scraped_data:
            output_file = generate_output_filename(config, output_dir)
            save_results(scraper.scraped_data, config, output_file)
        
        # 실패한 URL 저장
        if scraper.failed_urls:
            save_failed_urls(scraper.failed_urls, output_dir)
        
        # 최종 결과 리포트
        logger.info(f"크롤링 완료!")
        logger.info(f"소요 시간: {duration}")
        logger.info(f"성공: {len(scraper.scraped_data)}개")
        logger.info(f"실패: {len(scraper.failed_urls)}개")
        
        if scraper.scraped_data:
            success_rate = len(scraper.scraped_data) / len(urls) * 100
            logger.info(f"성공률: {success_rate:.1f}%")
        
    except KeyboardInterrupt:
        print("\n크롤링이 사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()