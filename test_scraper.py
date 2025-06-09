"""
네이버 뉴스 HTML 추출 테스트 스크립트
전체 본문 영역을 하나의 HTML 파일로 합치기
"""

import argparse
import logging
import time
import sys
from datetime import datetime
from typing import List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

from utils import (
    load_config, load_urls, setup_logger, create_output_directory,
    validate_config, get_system_info
)


class NaverNewsHTMLExtractor:
    """네이버 뉴스 HTML 추출 클래스"""
    
    def __init__(self, config):
        """
        HTML 추출기 초기화
        
        Args:
            config: 설정 딕셔너리
        """
        self.config = config
        self.logger = logging.getLogger('naver_scraper')
        self.extracted_htmls = []
        self.failed_urls = []
        
        # 네이버 뉴스 본문 영역 선택자들 (우선순위 순)
        self.article_selectors = [
            "div#newsct_article",           # 가장 일반적인 본문 영역
            "div.news_end_body_container",  # 다른 형태의 본문
            "div#articleBody",              # 또 다른 형태
            "div.article_body",             # 예비 선택자
            "article",                      # HTML5 article 태그
        ]
    
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
    
    def _extract_article_html(self, driver: webdriver.Chrome, url: str) -> Optional[str]:
        """
        단일 기사의 본문 영역 HTML 추출
        
        Args:
            driver: WebDriver 인스턴스
            url: 기사 URL
            
        Returns:
            추출된 HTML 문자열 또는 None
        """
        try:
            # 페이지 로드
            driver.get(url)
            
            # 페이지 로드 완료 대기
            WebDriverWait(driver, self.config['selenium']['page_load_timeout']).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 본문 영역 찾기 (여러 선택자 시도)
            article_element = None
            used_selector = ""
            
            for selector in self.article_selectors:
                try:
                    article_element = driver.find_element(By.CSS_SELECTOR, selector)
                    if article_element:
                        used_selector = selector
                        self.logger.debug(f"본문 영역 발견 ({selector}): {url}")
                        break
                except NoSuchElementException:
                    continue
            
            if not article_element:
                self.logger.warning(f"본문 영역을 찾을 수 없음: {url}")
                return None
            
            # HTML 추출
            article_html = article_element.get_attribute('outerHTML')
            
            if not article_html or len(article_html.strip()) == 0:
                self.logger.warning(f"빈 HTML 추출: {url}")
                return None
            
            self.logger.info(f"HTML 추출 성공 ({used_selector}): {url}")
            self.logger.debug(f"HTML 크기: {len(article_html):,} 문자")
            
            return article_html
            
        except TimeoutException:
            self.logger.error(f"페이지 로드 타임아웃: {url}")
            return None
        except WebDriverException as e:
            self.logger.error(f"WebDriver 오류 ({url}): {e}")
            return None
        except Exception as e:
            self.logger.error(f"예상치 못한 오류 ({url}): {e}")
            return None
    
    def extract_all_htmls(self, urls: List[str]) -> None:
        """
        모든 URL에서 HTML 추출 (순차 처리)
        
        Args:
            urls: 추출할 URL 리스트
        """
        delay = self.config['scraping'].get('delay_between_requests', 2.0)
        retry_count = self.config['scraping'].get('retry_count', 3)
        
        self.logger.info(f"HTML 추출 시작: {len(urls)}개 URL (순차 처리, 요청 간격: {delay}초)")
        
        # 단일 WebDriver 생성
        driver = None
        try:
            driver = self._create_driver()
            self.logger.info("Chrome 브라우저 시작")
            
            # 진행률 표시를 위한 tqdm 설정
            for url in tqdm(urls, desc="HTML 추출 진행", unit="URL"):
                try:
                    article_html = self._extract_article_html(driver, url)
                    if article_html:
                        # URL과 함께 저장
                        self.extracted_htmls.append({
                            'url': url,
                            'html': article_html,
                            'extracted_at': datetime.now().isoformat()
                        })
                        self.logger.debug(f"성공: {url}")
                    else:
                        self.failed_urls.append(url)
                        self.logger.warning(f"HTML 추출 실패: {url}")
                
                except Exception as e:
                    self.logger.error(f"추출 오류 ({url}): {e}")
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
        
        self.logger.info(f"HTML 추출 완료: 성공 {len(self.extracted_htmls)}개, 실패 {len(self.failed_urls)}개")
    
    def save_combined_html(self, output_file: str) -> None:
        """
        추출된 모든 HTML을 하나의 파일로 합쳐서 저장
        
        Args:
            output_file: 출력 파일 경로
        """
        if not self.extracted_htmls:
            self.logger.warning("저장할 HTML이 없습니다")
            return
        
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # HTML 템플릿 시작
            combined_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>네이버 뉴스 모음 - {timestamp}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .article-container {{
            margin-bottom: 40px;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .article-header {{
            background-color: #00c73c;
            color: white;
            padding: 15px;
        }}
        .article-url {{
            font-size: 14px;
            opacity: 0.9;
            word-break: break-all;
        }}
        .article-content {{
            padding: 20px;
        }}
        .extraction-info {{
            font-size: 12px;
            color: #666;
            text-align: right;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>네이버 뉴스 HTML 모음</h1>
        <p>추출 시간: {timestamp}</p>
        <p>총 {len(self.extracted_htmls)}개 기사</p>
    </div>
"""

            # 각 기사 HTML 추가
            for i, item in enumerate(self.extracted_htmls, 1):
                url = item['url']
                html = item['html']
                extracted_at = item['extracted_at']
                
                combined_html += f"""
    <div class="article-container">
        <div class="article-header">
            <h2>기사 {i}</h2>
            <div class="article-url">{url}</div>
            <div class="extraction-info">추출 시간: {extracted_at}</div>
        </div>
        <div class="article-content">
            {html}
        </div>
    </div>
"""

            # HTML 템플릿 종료
            combined_html += """
</body>
</html>"""

            # 파일 저장
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(combined_html)
            
            self.logger.info(f"통합 HTML 저장 완료: {output_file}")
            self.logger.info(f"총 {len(self.extracted_htmls)}개 기사, 파일 크기: {len(combined_html):,} 문자")
            
        except Exception as e:
            self.logger.error(f"HTML 파일 저장 실패: {e}")
            raise


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='네이버 뉴스 HTML 추출 테스트')
    parser.add_argument('--urls', required=True, help='URL 목록 파일 경로')
    parser.add_argument('--config', default='config.json', help='설정 파일 경로')
    parser.add_argument('--output', default='output/', help='출력 디렉토리')
    
    args = parser.parse_args()
    
    try:
        # 설정 로드 및 검증
        config = load_config(args.config)
        if not validate_config(config):
            sys.exit(1)
        
        # 로깅 설정
        logger = setup_logger(config)
        
        # 시스템 정보 로그
        system_info = get_system_info()
        logger.info(f"시스템 정보: {system_info}")
        
        # URL 로드
        urls = load_urls(args.urls)
        if not urls:
            logger.error("추출할 URL이 없습니다")
            sys.exit(1)
        
        # 출력 디렉토리 생성
        output_dir = create_output_directory(args.output)
        
        # HTML 추출기 실행
        extractor = NaverNewsHTMLExtractor(config)
        start_time = datetime.now()
        
        # HTML 추출
        extractor.extract_all_htmls(urls)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        # 통합 HTML 파일 저장
        if extractor.extracted_htmls:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"{output_dir}/naver_news_combined_{timestamp}.html"
            extractor.save_combined_html(output_file)
        
        # 실패한 URL 저장
        if extractor.failed_urls:
            from utils import save_failed_urls
            save_failed_urls(extractor.failed_urls, output_dir)
        
        # 최종 결과 리포트
        logger.info(f"HTML 추출 완료!")
        logger.info(f"소요 시간: {duration}")
        logger.info(f"성공: {len(extractor.extracted_htmls)}개")
        logger.info(f"실패: {len(extractor.failed_urls)}개")
        
        if extractor.extracted_htmls:
            success_rate = len(extractor.extracted_htmls) / len(urls) * 100
            logger.info(f"성공률: {success_rate:.1f}%")
        
    except KeyboardInterrupt:
        print("\nHTML 추출이 사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()