# test_service_account.py
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

def test_connection():
    try:
        credentials = Credentials.from_service_account_file(
            'auth/credentials.json',
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        
        service = build('drive', 'v3', credentials=credentials)
        
        # 서비스 계정 정보 확인
        about = service.about().get(fields="user").execute()
        print(f"연결 성공!")
        print(f"서비스 계정 이메일: {about['user']['emailAddress']}")
        
    except Exception as e:
        print(f"연결 실패: {e}")

if __name__ == "__main__":
    test_connection()