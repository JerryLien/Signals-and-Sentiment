FROM python:3.14-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式碼
COPY ptt_scraper/ ptt_scraper/
COPY reddit_scraper/ reddit_scraper/
COPY llm_agent/ llm_agent/
COPY data/ data/
COPY main.py scheduler.py ./

# 預設跑 scheduler (PTT + Reddit 雙源)
ENTRYPOINT ["python", "scheduler.py"]
CMD ["--source", "both", "--interval", "5"]
