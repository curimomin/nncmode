# drive_uploader.py
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials


class DriveUploader:
    def __init__(self, credentials_path):
        # 서비스 계정 사용
        self.credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        self.service = build('drive', 'v3', credentials=self.credentials)

    def upload_file(self, file_path, file_name=None, folder_id=None):
        """파일을 Google Drive에 업로드"""
        if not file_name:
            file_name = os.path.basename(file_path)

        file_metadata = {'name': file_name}

        # 특정 폴더에 업로드하려면
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(file_path, resumable=True)

        try:
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            print(f"파일 업로드 완료: {file_name}")
            print(f"파일 ID: {file.get('id')}")
            return file.get('id')

        except Exception as e:
            print(f"업로드 실패: {e}")
            return None

    def list_files(self, query=None, max_results=10):
        """
        Drive 파일 목록 조회 (선택적 기능)

        Args:
            query (str, optional): 검색 쿼리
            max_results (int): 최대 결과 수

        Returns:
            list: 파일 목록
        """
        try:
            if query:
                results = self.service.files().list(
                    q=query,
                    pageSize=max_results,
                    fields="nextPageToken, files(id, name, createdTime)"
                ).execute()
            else:
                results = self.service.files().list(
                    pageSize=max_results,
                    fields="nextPageToken, files(id, name, createdTime)"
                ).execute()

            return results.get('files', [])

        except Exception as e:
            print(f"파일 목록 조회 실패: {e}")
            return []

    def delete_file(self, file_id):
        """
        파일 ID로 파일 삭제

        Args:
            file_id (str): 삭제할 파일의 ID

        Returns:
            bool: 삭제 성공 여부
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            print(f"파일 삭제 완료: {file_id}")
            return True

        except Exception as e:
            print(f"파일 삭제 실패: {e}")
            return False

def main():
    # CSV 파일 생성 후 업로드
    file_path = "output/results.csv"

    if os.path.exists(file_path):
        uploader = DriveUploader('auth/credentials.json')
        uploader.upload_file(file_path)
    else:
        print("CSV 파일이 생성되지 않았습니다.")


if __name__ == "__main__":
    main()
