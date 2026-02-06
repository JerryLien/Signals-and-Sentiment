PTT_BASE_URL = "https://www.ptt.cc"

DEFAULT_BOARD = "Stock"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Cookie": "over18=1",
}

# 每次請求間的延遲秒數，避免被鎖 IP
REQUEST_DELAY = 0.5

# 推文情緒權重
PUSH_WEIGHT = 1.0    # 推
BOO_WEIGHT = -1.5    # 噓
ARROW_WEIGHT = 0.0   # → (中性)
