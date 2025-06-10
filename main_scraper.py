"""
네이버 뉴스 통합 스크래퍼 메인 모듈
기사 정보 + 댓글 데이터를 articles.csv와 comments.csv로 저장
"""

import argparse
import logging
import time
import sys
import csv
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from pathlib import Path

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
    validate_config, get_system_info
)

from drive_uploader import DriveUploader


class NaverNewsMainScraper:
    """네이버 뉴스 통합 크롤러 클래스"""

    def __init__(self, config: Dict[str, Any]):
        """
        크롤러 초기화

        Args:
            config: 설정 딕셔너리
        """
        self.config = config
        self.logger = logging.getLogger('naver_scraper')
        self.articles_data = []
        self.comments_data = []
        self.failed_urls = []
        self.selectors = config['naver_selectors']
        self.ui_labels = config['ui_labels']

        # ID 카운터
        self.article_id_counter = 1
        self.comment_id_counter = 1

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
        driver.set_page_load_timeout(
            selenium_config.get('page_load_timeout', 30))
        driver.set_script_timeout(selenium_config.get('script_timeout', 30))

        # 윈도우 크기 설정
        window_size = selenium_config.get('window_size', {})
        if window_size:
            driver.set_window_size(
                window_size.get('width', 1920),
                window_size.get('height', 1080)
            )

        return driver

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
                    text = elements[0].get_attribute(
                        'textContent') or elements[0].text
                    return text.strip()
            except Exception as e:
                self.logger.debug(f"선택자 '{sel}' 실패: {e}")
                continue

        return ""

    def _extract_number_from_text(self, text: str) -> str:
        """텍스트에서 숫자만 추출"""
        if not text:
            return ""

        numbers = re.findall(r'\d+', text)
        return numbers[0] if numbers else ""

    def _extract_article_data(self, driver: webdriver.Chrome, url: str) -> Optional[Dict[str, Any]]:
        """
        기사 페이지에서 기본 정보 추출

        Args:
            driver: WebDriver 인스턴스
            url: 기사 URL

        Returns:
            추출된 기사 데이터
        """
        try:
            # 페이지 로드
            driver.get(url)

            # 페이지 로드 완료 대기
            WebDriverWait(driver, self.config['selenium']['page_load_timeout']).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            scraped_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 기본 데이터 추출
            article_data = {
                'article_id': self.article_id_counter,
                'url': url,
                'title': self._extract_text_by_selector(driver, self.selectors['article']['title']),
                'content': self._extract_text_by_selector(driver, self.selectors['article']['content']),
                'author': self._extract_text_by_selector(driver, self.selectors['article']['author']),
                'publish_date': self._extract_text_by_selector(driver, self.selectors['article']['publish_date']),
                'category': self._extract_text_by_selector(driver, self.selectors['article']['category']),
                'like_count': self._extract_number_from_text(
                    self._extract_text_by_selector(
                        driver, self.selectors['article']['like_count'])
                ),
                'comment_count': self._extract_number_from_text(
                    self._extract_text_by_selector(
                        driver, self.selectors['article']['comment_count'])
                ),
                'scraped_at': scraped_at
            }

            # 댓글 통계 필드 초기화 (빈 값)
            article_data.update({
                'active_comment_count': "",
                'deleted_comment_count': "",
                'removed_comment_count': "",
                'male_ratio': "",
                'female_ratio': "",
                'age_10s_ratio': "",
                'age_20s_ratio': "",
                'age_30s_ratio': "",
                'age_40s_ratio': "",
                'age_50s_ratio': "",
                'age_60plus_ratio': ""
            })

            # 필수 필드 검증
            if not article_data['title']:
                self.logger.warning(f"제목이 없는 기사: {url}")
                return None

            self.logger.debug(f"기사 데이터 추출 성공: {url}")
            return article_data

        except Exception as e:
            self.logger.error(f"기사 데이터 추출 실패 ({url}): {e}")
            return None

    def _navigate_to_comments_page(self, driver: webdriver.Chrome) -> bool:
        """
        기사 페이지에서 댓글 페이지로 이동

        Args:
            driver: WebDriver 인스턴스

        Returns:
            댓글 페이지 이동 성공 여부
        """
        try:
            # 댓글 더보기 버튼 찾기
            comment_button = driver.find_element(
                By.CSS_SELECTOR,
                self.selectors['comment_navigation']['article_to_comment_button']
            )

            if comment_button.is_displayed():
                comment_button.click()

                # 페이지 로드 대기
                time.sleep(3)
                return True
            else:
                self.logger.warning("댓글 버튼이 보이지 않음")
                return False

        except NoSuchElementException:
            self.logger.warning("댓글 더보기 버튼을 찾을 수 없음")
            return False
        except Exception as e:
            self.logger.error(f"댓글 페이지 이동 실패: {e}")
            return False

    def _load_all_comments(self, driver: webdriver.Chrome) -> None:
        """
        댓글 페이지에서 모든 댓글 로드 (더보기 반복 클릭)

        Args:
            driver: WebDriver 인스턴스
        """
        try:
            while True:
                try:
                    # 댓글 페이지의 더보기 버튼 찾기
                    more_button = driver.find_element(
                        By.CSS_SELECTOR,
                        self.selectors['comment_navigation']['comment_page_more_button']
                    )

                    if more_button.is_displayed():
                        more_button.click()
                        self.logger.debug("댓글 더보기 버튼 클릭")
                        time.sleep(3)  # 로딩 대기
                    else:
                        break

                except NoSuchElementException:
                    break  # 더보기 버튼이 없으면 모든 댓글 로드 완료

        except Exception as e:
            self.logger.error(f"댓글 로드 중 오류: {e}")

    def _extract_comment_stats(self, driver: webdriver.Chrome, article_data: Dict[str, Any]) -> None:
        """
        댓글 일반통계 정보 추출 및 기사 데이터 업데이트

        Args:
            driver: WebDriver 인스턴스
            article_data: 업데이트할 기사 데이터
        """
        
        try:
            stat_items = driver.find_elements(
                By.CSS_SELECTOR, self.selectors['comment_stats']['stat_count_info'])

            # 기본값 설정
            article_data['active_comment_count'] = 0
            article_data['deleted_comment_count'] = 0
            article_data['removed_comment_count'] = 0

            for item in stat_items:
                title = self._extract_text_by_selector(
                    item, self.selectors['comment_stats']['stat_title'])
                value_text = self._extract_text_by_selector(
                    item, self.selectors['comment_stats']['stat_value'])
                value = self._extract_number_from_text(value_text)

                if self.ui_labels['comments']['current_comment_count'] in title:
                    article_data['active_comment_count'] = value
                elif self.ui_labels['comments']['deleted_comment_count'] in title:
                    article_data['deleted_comment_count'] = value
                elif self.ui_labels['comments']['removed_comment_count'] in title:
                    article_data['removed_comment_count'] = value

            self.logger.debug("  ├─ 댓글 일반통계 추출 완료")

        except Exception as e:
            self.logger.warning(f"댓글 일반통계 추출 실패: {e}")

    def _extract_comment_demographic_stats(self, driver: webdriver.Chrome, article_data: Dict[str, Any]) -> None:
        """
        댓글 상세통계 정보 추출 및 기사 데이터 업데이트

        Args:
            driver: WebDriver 인스턴스
            article_data: 업데이트할 기사 데이터
        """
        try:
            chart_wrap_element = driver.find_element(
                By.CSS_SELECTOR, self.selectors['comment_stats']['demographic_stats_container'])

            if not chart_wrap_element.is_displayed():
                self.logger.info("  ├─ 댓글 상세통계 차트 요소를 찾을 수 없음")
                return

            # 성별 비율 추출
            article_data['male_ratio'] = self._extract_number_from_text(
                self._extract_text_by_selector(
                    driver, self.selectors['comment_stats']['male_ratio'])
            )
            article_data['female_ratio'] = self._extract_number_from_text(
                self._extract_text_by_selector(
                    driver, self.selectors['comment_stats']['female_ratio'])
            )

            # 연령대 비율 추출
            age_chart_container = driver.find_element(
                By.CSS_SELECTOR, ".u_cbox_chart_age")
            age_items = age_chart_container.find_elements(
                By.CSS_SELECTOR, ".u_cbox_chart_progress")

            for item in age_items:
                age_text = self._extract_text_by_selector(
                    item, ".u_cbox_chart_cnt span")
                percentage_text = self._extract_text_by_selector(
                    item, ".u_cbox_chart_per")
                percentage = self._extract_number_from_text(percentage_text)

                if self.ui_labels['comments']['10s'] in age_text:
                    article_data['age_10s_ratio'] = percentage
                elif self.ui_labels['comments']['20s'] in age_text:
                    article_data['age_20s_ratio'] = percentage
                elif self.ui_labels['comments']['30s'] in age_text:
                    article_data['age_30s_ratio'] = percentage
                elif self.ui_labels['comments']['40s'] in age_text:
                    article_data['age_40s_ratio'] = percentage
                elif self.ui_labels['comments']['50s'] in age_text:
                    article_data['age_50s_ratio'] = percentage
                elif self.ui_labels['comments']['60s'] in age_text:
                    article_data['age_60plus_ratio'] = percentage

        except Exception as e:
            self.logger.warning(f"댓글 상세통계 추출 실패: {e}")

    def _extract_comments_data(self, driver: webdriver.Chrome, article_id: int) -> None:
        """
        댓글 데이터 추출

        Args:
            driver: WebDriver 인스턴스
            article_id: 기사 ID
        """
        
        try:
            
            scraped_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 모든 댓글 요소 찾기
            comment_elements = driver.find_elements(
                By.CSS_SELECTOR,
                self.selectors['comments']['comment_list']
            )

            self.logger.info(f"  ├─ 발견된 댓글 수: {len(comment_elements)}")
            
            comment_count = len(driver.find_elements(By.CSS_SELECTOR, self.selectors['comments']['comment_list']))

            for i in range(comment_count):

                try:
                  
                    comment_elements = driver.find_elements(
                        By.CSS_SELECTOR,
                        self.selectors['comments']['comment_list'])
                    comment_element = comment_elements[i]

                    # data-info 속성에서 댓글 정보 추출
                    data_info = comment_element.get_attribute('data-info')
                    if not data_info:
                        continue


                    # 삭제된 댓글인지 확인
                    is_deleted = 'deleted:true' in data_info

                    if is_deleted:
                        # 삭제된 댓글의 경우 제한된 정보만 추출
                        content = "삭제된 댓글입니다"
                        author = self._extract_text_by_selector(
                            comment_element, self.selectors['comments']['deleted_comment_author'])
                        like_count = ""
                        dislike_count = ""
                    else:
                        # 일반 댓글 정보 추출
                        content = self._extract_text_by_selector(
                            comment_element, self.selectors['comments']['comment_content'])
                        author = self._extract_text_by_selector(
                            comment_element, self.selectors['comments']['comment_author'])
                        like_count = self._extract_number_from_text(
                            self._extract_text_by_selector(
                                comment_element, self.selectors['comments']['comment_like'])
                        )
                        dislike_count = self._extract_number_from_text(
                            self._extract_text_by_selector(
                                comment_element, self.selectors['comments']['comment_dislike'])
                        )


                    # 작성 날짜 추출
                    created_at = self._extract_text_by_selector(
                        comment_element, self.selectors['comments']['comment_date'])

                    # 댓글 데이터 생성
                    comment_data = {
                        'article_id': article_id,
                        'comment_id': self.comment_id_counter,
                        'content': content,
                        'author': author,
                        'like_count': like_count,
                        'dislike_count': dislike_count,
                        'created_at': created_at,
                        'scraped_at': scraped_at
                    }

                    self.comments_data.append(comment_data)
                    self.comment_id_counter += 1

                except Exception as e:
                    self.logger.debug(f"개별 댓글 처리 실패: {e}")
                    continue

            self.logger.info(f"  ├─ 댓글 추출 완료: {len(comment_elements)}개")

        except Exception as e:
            self.logger.error(f"댓글 데이터 추출 실패: {e}")
            
    

    def _disable_cleanbot(self, driver: webdriver.Chrome) -> None:
      try:
          # 클린봇 컨테이너 찾기
          cleanbot_container = driver.find_element(
              By.CSS_SELECTOR, self.selectors['cleanbot']["cleanbot_container"])
          
          # 클린봇 해제 점검
          cleanbot_message = self._extract_text_by_selector(
              cleanbot_container, self.selectors['cleanbot']["cleanbot_message"])
          
          if cleanbot_message and "착한댓글" in cleanbot_message:
              self.logger.info("  ├─ 클린봇 해제 확인")
              return
            
          setting_button = cleanbot_container.find_element(
              By.CSS_SELECTOR, self.selectors['cleanbot']["setting_button"])

          if setting_button.is_displayed():
              setting_button.click()
              print("    ✓ 설정 버튼 클릭 - 모달창 대기중...")
              time.sleep(3)  # 모달 생성 대기 시간 증가

              # 정확한 모달 선택자들 (실제 HTML 구조 기반)
              modal_selectors = {
                  "cleanbot_modal": ".u_cbox_layer_wrap, .u_cbox_layer_cleanbot2_wrap, .u_cbox_layer_cleanbot2, .u_cbox_layer_cleanbot2_content"
              }

              # 체크박스 선택자들 (실제 HTML 구조 기반)
              checkbox_selectors = {
                  "cleanbot_checkbox": "#cleanbot_dialog_checkbox_cbox_module, .u_cbox_layer_cleanbot2_checkbox, input[data-action='toggleCleanbot2']"
              }

              # 확인 버튼 선택자들 (실제 HTML 구조 기반)
              confirm_selectors = {
                  "confirm_button": "button[data-action='updateCleanbotStatus'], .u_cbox_layer_cleanbot2_extrabtn"
              }

              # 모달창 찾기
              modal = None
              for key, selector_string in modal_selectors.items():
                  selectors = [s.strip() for s in selector_string.split(',')]
                  for selector in selectors:
                      try:
                          modal = driver.find_element(By.CSS_SELECTOR, selector)
                          if modal and modal.is_displayed():
                              print(f"    ✓ 모달창 발견: {key} -> {selector}")
                              break
                      except:
                          continue
                  if modal and modal.is_displayed():
                      break

              if not modal or not modal.is_displayed():
                  self.logger.warning("CleanBot 설정 모달을 찾을 수 없음")
                  return

              # 체크박스 찾기 및 상태 확인
              checkbox = None
              for key, selector_string in checkbox_selectors.items():
                  selectors = [s.strip() for s in selector_string.split(',')]
                  for selector in selectors:
                      try:
                          checkbox = modal.find_element(
                              By.CSS_SELECTOR, selector)
                          if checkbox:
                              print(f"    ✓ 체크박스 발견: {key} -> {selector}")
                              break
                      except:
                          continue
                  if checkbox:
                      break

              if not checkbox:
                  self.logger.warning("CleanBot 체크박스를 찾을 수 없음")
                  return

              # 체크박스 상태 확인 (is_checked 클래스 여부)
              checkbox_classes = checkbox.get_attribute('class') or ""
              is_checked = "is_checked" in checkbox_classes
              print(f"    ✓ 현재 클린봇 상태: {'활성화' if is_checked else '비활성화'}")

              # 클린봇이 활성화되어 있으면 비활성화
              if is_checked:
                  try:
                      # 체크박스 클릭 시도
                      driver.execute_script("arguments[0].click();", checkbox)
                      print("    ✓ 클린봇 체크박스 클릭됨")
                      time.sleep(1)
                  except Exception as e:
                      print(f"    ! 체크박스 직접 클릭 실패: {e}")
                      try:
                          # 더미 체크박스 클릭 시도
                          dummy_checkbox = modal.find_element(
                              By.CSS_SELECTOR, ".u_cbox_layer_cleanbot2_checkboxdummy")
                          driver.execute_script(
                              "arguments[0].click();", dummy_checkbox)
                          print("    ✓ 더미 체크박스 클릭됨")
                          time.sleep(1)
                      except Exception as e2:
                          print(f"    ! 더미 체크박스 클릭도 실패: {e2}")
                          try:
                              # 레이블 클릭 시도
                              label = modal.find_element(
                                  By.CSS_SELECTOR, "label[for='cleanbot_dialog_checkbox_cbox_module']")
                              driver.execute_script(
                                  "arguments[0].click();", label)
                              print("    ✓ 레이블 클릭됨")
                              time.sleep(1)
                          except Exception as e3:
                              self.logger.warning(f"모든 체크박스 클릭 방법 실패: {e3}")
                              return

                  # 상태 변경 확인
                  updated_checkbox = modal.find_element(
                      By.CSS_SELECTOR, "#cleanbot_dialog_checkbox_cbox_module")
                  updated_classes = updated_checkbox.get_attribute('class') or ""
                  is_still_checked = "is_checked" in updated_classes

                  if not is_still_checked:
                      print("    ✓ 클린봇이 성공적으로 비활성화됨")

                      # 확인 버튼 클릭
                      confirm_button = None
                      for key, selector_string in confirm_selectors.items():
                          selectors = [s.strip()
                                      for s in selector_string.split(',')]
                          for selector in selectors:
                              try:
                                  confirm_button = modal.find_element(
                                      By.CSS_SELECTOR, selector)
                                  if confirm_button and confirm_button.is_displayed():
                                      print(f"    ✓ 확인 버튼 발견: {key} -> {selector}")
                                      break
                              except:
                                  continue
                          if confirm_button and confirm_button.is_displayed():
                              break

                      if confirm_button:
                          driver.execute_script(
                              "arguments[0].click();", confirm_button)
                          print("    ✓ 확인 버튼 클릭 - 설정 저장됨")
                          time.sleep(1)
                          self.logger.info("  ├─ CleanBot 비활성화 완료")
                      else:
                          self.logger.warning("확인 버튼을 찾을 수 없음")
                  else:
                      self.logger.warning("클린봇 비활성화에 실패함")
              else:
                  self.logger.debug("클린봇이 이미 비활성화되어 있음")
                  # 이미 비활성화된 경우에도 확인 버튼 클릭해서 모달 닫기
                  confirm_button = modal.find_element(
                      By.CSS_SELECTOR, "button[data-action='updateCleanbotStatus']")
                  if confirm_button:
                      driver.execute_script(
                          "arguments[0].click();", confirm_button)
                      print("    ✓ 모달창 닫기")

          else:
              self.logger.warning("CleanBot 설정 버튼이 보이지 않음")
              return

      except Exception as e:
          self.logger.warning(f"CleanBot 방지 기능 비활성화 실패: {e}")
          # 에러 발생 시 모달이 열려있다면 닫기 시도
          try:
              close_button = driver.find_element(
                  By.CSS_SELECTOR, "button[data-action='closeCleanbotLayer']")
              if close_button and close_button.is_displayed():
                  driver.execute_script("arguments[0].click();", close_button)
                  self.logger.warning("에러 발생으로 모달창 강제 닫기")
          except:
              pass

    def _process_single_url(self, driver: webdriver.Chrome, url: str) -> bool:
        """
        단일 URL의 기사 + 댓글 처리

        Args:
            driver: WebDriver 인스턴스
            url: 처리할 URL

        Returns:
            처리 성공 여부
        """
        try:
            self.logger.info(f"처리 시작: {url}")

            # 1. 기사 데이터 추출
            self.logger.info(f"  ├─ 기사데이터 추출시작")
            article_data = self._extract_article_data(driver, url)
            if not article_data:
                return False

            current_article_id = article_data['article_id']

            # 1.1 댓글 추가작업 진행여부 판단 및 진행
            sohuld_process_additional_comments_work = article_data['comment_count'] != "0"
            if not sohuld_process_additional_comments_work:
                self.logger.info(
                    f"  ├─ 댓글이 없는 기사 데이터만 저장")
                self.logger.info(f"  └─ 처리 완료 {'─' * 60}")
                # 댓글이 없는 경우, 기사 데이터만 저장하고 종료
                self.articles_data.append(article_data)
                self.article_id_counter += 1
                return True


            # 2. 댓글 통계 추출 및 기사 데이터 업데이트
            self.logger.info(f"  ├─ 댓글 일반통계 추출시작")
            self._extract_comment_stats(driver, article_data)

            # 3. 댓글 상세 통계 추출
            self.logger.info(f"  ├─ 댓글 상세통계 추출시작")
            self._extract_comment_demographic_stats(driver, article_data)

            # 4. 댓글 페이지로 이동
            self.logger.info(f"  ├─ 댓글 페이지로 이동")
            if self._navigate_to_comments_page(driver):
                
                # 5. 클린봇 해제
                self.logger.info(f"  ├─ 클린봇 해제 시작")
                self._disable_cleanbot(driver)
                
                # 6. 모든 댓글 로드
                self.logger.info(f"  ├─ 댓글 로드 시작")
                self._load_all_comments(driver)

                # 7. 댓글 데이터 추출
                self.logger.info(f"  ├─ 댓글 추출 시작")
                self._extract_comments_data(driver, current_article_id)
            else:
                self.logger.warning(f"  ├─ 댓글 페이지 접근 실패, 기사 데이터만 저장: {url}")

            # 8. 기사 데이터 저장
            self.logger.info(f"  ├─ 기사 데이터 저장(메모리)")
            self.articles_data.append(article_data)
            self.article_id_counter += 1

            self.logger.info(f"  └─ 처리 완료 {'─' * 60}")
            return True

        except Exception as e:
            self.logger.error(f"URL 처리 실패 ({url}): {e}")
            return False

    def scrape_urls(self, urls: List[str]) -> None:
        """
        URL 목록 크롤링 (순차 처리)

        Args:
            urls: 크롤링할 URL 리스트
        """
        delay = self.config['scraping'].get('delay_between_requests', 3.0)

        self.logger.info(
            f"통합 크롤링 시작: {len(urls)}개 URL (순차 처리, 요청 간격: {delay}초)")

        # 단일 WebDriver 생성
        driver = None
        try:
            driver = self._create_driver()
            self.logger.info("Chrome 브라우저 시작")

            # 진행률 표시를 위한 tqdm 설정
            for url in tqdm(urls, desc="통합 크롤링 진행", unit="URL"):
                try:
                    success = self._process_single_url(driver, url)
                    if not success:
                        self.failed_urls.append(url)

                except Exception as e:
                    self.logger.error(f"URL 처리 오류 ({url}): {e}")
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

        self.logger.info(
            f"통합 크롤링 완료: 성공 {len(self.articles_data)}개, 실패 {len(self.failed_urls)}개")

    def save_csv_files(self, output_dir: str, suffix: str) -> None:
        """
        articles.csv와 comments.csv 파일 저장

        Args:
            output_dir: 출력 디렉토리
            suffix: 파일 접미사 (입력받은 urls 파일명)
        """
        try:
            # articles.csv 저장
            if self.articles_data:
                # suffix에서 파일명 추출
                clean_suffix = Path(suffix).stem
                # suffix기반 파일명 생성
                articles_file = Path(output_dir) / f"articles_{clean_suffix}.csv"
                with open(articles_file, 'w', newline='', encoding='utf-8') as f:
                    fieldnames = [
                        'article_id', 'url', 'title', 'content', 'author', 'publish_date', 'category',
                        'like_count', 'comment_count', 'active_comment_count', 'deleted_comment_count',
                        'removed_comment_count', 'male_ratio', 'female_ratio', 'age_10s_ratio',
                        'age_20s_ratio', 'age_30s_ratio', 'age_40s_ratio', 'age_50s_ratio',
                        'age_60plus_ratio', 'scraped_at'
                    ]
                    writer = csv.DictWriter(
                        f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                    writer.writeheader()
                    writer.writerows(self.articles_data)

                self.logger.info(
                    f"articles.csv 저장 완료: {len(self.articles_data)}개 기사")

            # comments.csv 저장
            if self.comments_data:
                comments_file = Path(output_dir) / f"comments_{clean_suffix}.csv"
                with open(comments_file, 'w', newline='', encoding='utf-8') as f:
                    fieldnames = [
                        'article_id', 'comment_id', 'parent_comment_id', 'comment_type',
                        'content', 'author', 'like_count', 'dislike_count', 'reply_count',
                        'created_at', 'scraped_at'
                    ]
                    writer = csv.DictWriter(
                        f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
                    writer.writeheader()
                    writer.writerows(self.comments_data)

                self.logger.info(
                    f"comments.csv 저장 완료: {len(self.comments_data)}개 댓글")

        except Exception as e:
            self.logger.error(f"CSV 파일 저장 실패: {e}")
            raise


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='네이버 뉴스 통합 크롤러 (기사 + 댓글)')
    parser.add_argument('--urls', required=True, help='URL 목록 파일 경로')
    parser.add_argument('--config', default='config.json', help='설정 파일 경로')
    parser.add_argument('--output', default='output/', help='출력 디렉토리')
    parser.add_argument('--upload', action='store_true', help='구글 드라이브에 작업내용 업로드')

    args = parser.parse_args()

    try:
        # 설정 로드 및 검증
        config = load_config(args.config)
        if not validate_config(config):
            sys.exit(1)

        # 로깅 설정
        logger = setup_logger(config)

        # 시작 로그
        logger.info("=" * 50)
        logger.info("🚀 네이버 뉴스 통합 크롤러 시작")
        logger.info("=" * 50)

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

        # 통합 크롤러 실행
        scraper = NaverNewsMainScraper(config)
        start_time = datetime.now()

        scraper.scrape_urls(urls)

        end_time = datetime.now()
        duration = end_time - start_time

        # CSV 파일 저장
        scraper.save_csv_files(output_dir, args.urls)

        # 실패한 URL 저장
        if scraper.failed_urls:
            from utils import save_failed_urls
            save_failed_urls(scraper.failed_urls, output_dir)

        # 구글 드라이브 업로드
        if args.upload:
            logger.info("구글 드라이브에 업로드 시작")
            
            # suffix기반 파일명 생성
            clean_suffix = Path(args.urls).stem
            articles_file = Path(output_dir) / f"articles_{clean_suffix}.csv"
            comments_file = Path(output_dir) / f"comments_{clean_suffix}.csv"
            try:
                uploader = DriveUploader('auth/credentials.json')
                uploader.upload_file(articles_file)
                logger.info(f"구글 드라이브에 articles 업로드 완료: {articles_file}")
                uploader.upload_file(comments_file)
                logger.info(f"구글 드라이브에 articles 업로드 완료: {comments_file}")
            except Exception as e:
                logger.warning(f"구글 드라이브에 업로드 실패: {e}")
                raise
            
            
        # 최종 결과 리포트
        logger.info(f"통합 크롤링 완료!")
        logger.info(f"소요 시간: {duration}")
        logger.info(f"성공한 기사: {len(scraper.articles_data)}개")
        logger.info(f"수집한 댓글: {len(scraper.comments_data)}개")
        logger.info(f"실패한 URL: {len(scraper.failed_urls)}개")

        if scraper.articles_data:
            success_rate = len(scraper.articles_data) / len(urls) * 100
            logger.info(f"성공률: {success_rate:.1f}%")

            # 댓글 통계
            avg_comments = len(scraper.comments_data) / \
                len(scraper.articles_data)
            logger.info(f"평균 댓글 수: {avg_comments:.1f}개/기사")

    except KeyboardInterrupt:
        print("\n크롤링이 사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
