# Welcome to NNC_MODE


## Notice
  1. 매번 작업할 때마다 source venv/bin/activate 실행 필요


## how to open html file
open -a "Google Chrome" output/naver_news_combined_20250609_175833.html

## memo
  1. 프로젝트 폴더로 이동
    cd /Users/curimomin/Desktop/side_projects/nncmode

  2. 가상환경 생성
    python3 -m venv venv

  3. 가상환경 활성화
    source venv/bin/activate

  4. 패키지 설치
    pip install -r requirements.txt

  5. 스크립트 실행
    python scraper.py --urls urls.txt


## Windows 에서 작업시
  1. git clone [url]
  2. py -m venv venv
  3. venv/Scripts/activate

### 가상환경 새로 생성
python -m venv venv

### 활성화
source venv/bin/activate  # Linux/Mac
### 또는
venv\Scripts\activate     # Windows

### 패키지 설치
pip install -r requirements.txt