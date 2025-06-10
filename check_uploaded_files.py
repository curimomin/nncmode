# check_uploaded_files.py
from drive_uploader import DriveUploader

def check_files():
    uploader = DriveUploader('auth/credentials.json')
    
    print("=== 서비스 계정 Drive의 파일 목록 ===")
    files = uploader.list_files(max_results=20)
    
    for file in files:
        print(f"파일명: {file['name']}")
        print(f"파일 ID: {file['id']}")
        print(f"링크: https://drive.google.com/file/d/{file['id']}/view")
        print(f"생성일: {file.get('createdTime', 'N/A')}")
        print("-" * 50)

if __name__ == "__main__":
    check_files()