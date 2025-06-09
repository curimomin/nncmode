# 네이버 뉴스 크롤링 CSV 스키마

## 개요
네이버 뉴스 기사와 댓글 데이터를 수집하여 2개의 CSV 파일로 저장하는 구조입니다.

## 파일 구조

### 1. articles.csv (기사 정보)
기사별 메타데이터와 본문 내용을 저장합니다.

| 필드명 | 데이터 타입 | 설명 | 예시 |
|--------|-------------|------|------|
| article_id | integer | 기사 고유 ID (1부터 순차 증가) | 1 |
| url | string | 기사 원본 URL | "https://n.news.naver.com/mnews/article/056/0011964101" |
| title | string | 기사 제목 | "기사 제목 예시" |
| content | string | 기사 본문 전체 내용 | "기사 본문 내용..." |
| author | string | 기자명 | "홍길동" |
| publish_date | string | 기사 발행일시 (YYYY-MM-DD HH:MM:SS) | "2024-06-09 14:30:00" |
| category | string | 기사 카테고리 | "정치" |
| like_count | string | 기사 추천수 | "150" |
| comment_count | string | 댓글 총 개수 | "45" |
| scraped_at | string | 크롤링 수행 시간 (YYYY-MM-DD HH:MM:SS) | "2024-06-09 17:55:42" |

### 2. comments.csv (댓글 정보)
기사별 댓글과 대댓글 정보를 저장합니다.

| 필드명 | 데이터 타입 | 설명 | 예시 |
|--------|-------------|------|------|
| article_id | integer | 기사 ID (articles.csv의 article_id 참조) | 1 |
| comment_id | integer | 댓글 고유 ID (전역 순번, 1부터 증가) | 1 |
| parent_comment_id | string | 부모 댓글 ID (원댓글이면 빈 문자열) | "1" 또는 "" |
| comment_type | string | 댓글 유형 ("comment" 또는 "reply") | "comment" |
| content | string | 댓글 내용 | "댓글 내용 예시" |
| author | string | 댓글 작성자명 | "사용자1" |
| like_count | string | 댓글 추천수 | "10" |
| dislike_count | string | 댓글 비추천수 | "2" |
| reply_count | string | 해당 댓글의 대댓글 개수 | "3" |
| created_at | string | 댓글 작성 시간 (YYYY-MM-DD HH:MM:SS) | "2024-06-09 15:30:00" |
| scraped_at | string | 크롤링 수행 시간 (YYYY-MM-DD HH:MM:SS) | "2024-06-09 17:55:42" |

## 데이터 규칙

### 일반 규칙
- **인코딩**: UTF-8
- **NULL 처리**: 모든 필드에서 빈 문자열 `""` 사용
- **CSV 이스케이프**: 모든 값을 따옴표로 감싸기
- **날짜 형식**: `YYYY-MM-DD HH:MM:SS`

### ID 관리
- **article_id**: 1부터 시작하는 순차 증가 integer
- **comment_id**: 전역적으로 1부터 시작하는 순차 증가 integer

### 댓글 계층 구조
- **원댓글**: `comment_type = "comment"`, `parent_comment_id = ""`
- **대댓글**: `comment_type = "reply"`, `parent_comment_id = "부모댓글의 comment_id"`
- **reply_count**: 해당 댓글에 달린 직접적인 대댓글 개수 (대댓글의 경우 항상 "0")

## CSV 예시

### articles.csv
```csv
article_id,url,title,content,author,publish_date,category,like_count,comment_count,scraped_at
1,"https://n.news.naver.com/mnews/article/056/0011964101","기사제목","기사본문전체","기자명","2024-06-09 14:30:00","정치","150","45","2024-06-09 17:55:42"
2,"https://n.news.naver.com/mnews/article/023/0003908588","제목만있는기사","","","2024-06-09 15:00:00","","","","2024-06-09 17:56:00"
```

### comments.csv
```csv
article_id,comment_id,parent_comment_id,comment_type,content,author,like_count,dislike_count,reply_count,created_at,scraped_at
1,1,"","comment","첫번째 댓글","사용자1","10","2","3","2024-06-09 15:30:00","2024-06-09 17:55:42"
1,2,"1","reply","첫번째 대댓글","사용자2","5","0","0","2024-06-09 15:35:00","2024-06-09 17:55:42"
1,3,"1","reply","두번째 대댓글","사용자3","2","1","0","2024-06-09 15:40:00","2024-06-09 17:55:42"
1,4,"1","reply","세번째 대댓글","사용자4","1","0","0","2024-06-09 15:45:00","2024-06-09 17:55:42"
1,5,"","comment","두번째 원댓글","사용자5","8","0","1","2024-06-09 16:00:00","2024-06-09 17:55:42"
1,6,"5","reply","두번째 원댓글의 대댓글","사용자6","3","0","0","2024-06-09 16:05:00","2024-06-09 17:55:42"
```

## 데이터 관계

### 기사-댓글 관계
- 1:N 관계 (하나의 기사에 여러 댓글)
- `articles.article_id = comments.article_id`로 연결

### 댓글-대댓글 관계
- 1:N 관계 (하나의 댓글에 여러 대댓글)
- `comments.comment_id = comments.parent_comment_id`로 연결

## 데이터 검증 쿼리 예시

### SQL 스타일 검증
```sql
-- 원댓글만 조회
SELECT * FROM comments WHERE comment_type = 'comment' AND parent_comment_id = '';

-- 특정 댓글의 모든 대댓글 조회
SELECT * FROM comments WHERE parent_comment_id = '1';

-- 기사별 댓글 통계
SELECT article_id, COUNT(*) as total_comments 
FROM comments 
GROUP BY article_id;

-- reply_count 검증
SELECT 
    c1.comment_id,
    c1.reply_count,
    COUNT(c2.comment_id) as actual_replies
FROM comments c1
LEFT JOIN comments c2 ON c1.comment_id = c2.parent_comment_id
WHERE c1.comment_type = 'comment'
GROUP BY c1.comment_id, c1.reply_count;
```

---

**작성일**: 2024-06-09  
**버전**: 1.0  
**프로젝트**: 네이버 뉴스 크롤러