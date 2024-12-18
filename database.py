from databases import Database
from dotenv import load_dotenv
import os

# .env 파일에서 환경 변수 로드
load_dotenv()

# DATABASE_URL 환경 변수에서 데이터베이스 URL을 가져옴
DATABASE_URL = os.getenv("DATABASE_URL")
database = Database(DATABASE_URL)
