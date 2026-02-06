REDDIT_BASE_URL = "https://www.reddit.com"

# 預設關注的 Subreddit
DEFAULT_SUBREDDITS: list[str] = [
    "wallstreetbets",
    "stocks",
    "investing",
    "cryptocurrency",
    "bitcoin",
]

# Reddit public JSON API 要求有意義的 User-Agent
HEADERS = {
    "User-Agent": "PTT-Signals-and-Sentiment/1.0 (market sentiment research)",
}

# Reddit rate limit: ~60 requests/min for unauthenticated
REQUEST_DELAY = 1.0

# 情緒關鍵字權重
BULLISH_WEIGHT = 1.0
BEARISH_WEIGHT = -1.0
