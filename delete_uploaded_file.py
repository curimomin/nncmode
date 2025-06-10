import argparse
from drive_uploader import DriveUploader


def delete_specific_file(file_id: str):
    uploader = DriveUploader('auth/credentials.json')

    print(f"파일 삭제 중: {file_id}")
    success = uploader.delete_file(file_id)
    
    if success:
        print("✅ 파일 삭제 완료!")
    else:
        print("❌ 파일 삭제 실패")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Google Drive 파일 삭제')
    parser.add_argument('--id', required=True, help='삭제할 파일의 ID')

    args = parser.parse_args()

    delete_specific_file(args.id)