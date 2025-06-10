# Welcome to NNC_MODE
📗 네이버 뉴스 크롤러


## Note
  1. 작업 전 가상환경 설정과 requirements 설치 필요

## Utils
  1. check_uploaded_files.py 

  2. delete_uploaded_file.py (사용시 --id [id] 입력필요) 

## Google Drive - service account
  1. drive_uploader.py

## Start Project (macOS)
  1. git clone [url]

  2. 프로젝트 폴더로 이동
    cd /Users/curimomin/Desktop/side_projects/nncmode

  3. 가상환경 생성
    python3 -m venv venv

  4. 가상환경 활성화
    source venv/bin/activate

  5. 패키지 설치
    pip install -r requirements.txt

  6. 테스트 파일 제거
    urls/test_1.txt 및 urls/test_2.txt 삭제

  7. 스크립트 실행
    python batch_scraper_runner.py --directory ./urls --pattern "*.txt"


## Start Project (windows)
  1. git clone [url]

  2. 프로젝트 폴더로 이동
    cd /Users/curimomin/Desktop/side_projects/nncmode

  3. 가상환경 생성
    py -m venv venv

  4. 가상환경 활성화
    venv/Scripts/activate

  5. 패키지 설치 (필요하다면 pip을 업데이트)
    pip install -r requirements.txt

  6. 테스트 파일 제거
    urls/test_1.txt 및 urls/test_2.txt 삭제

  7. 스크립트 실행
    py batch_scraper_runner_win.py --directory ./urls --pattern "*.txt"
