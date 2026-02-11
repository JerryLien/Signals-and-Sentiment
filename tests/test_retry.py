"""指數退避重試機制的測試。"""

import time
from unittest.mock import MagicMock, patch

from scheduler import _run_with_retry, MAX_RETRIES


class TestRunWithRetry:
    def test_success_on_first_attempt(self):
        func = MagicMock()
        _run_with_retry(func, "a", "b", key="val")
        func.assert_called_once_with("a", "b", key="val")

    def test_success_on_second_attempt(self):
        func = MagicMock(side_effect=[RuntimeError("fail"), None])
        with patch.object(time, "sleep"):
            _run_with_retry(func, "x")
        assert func.call_count == 2

    def test_gives_up_after_max_retries(self):
        func = MagicMock(side_effect=RuntimeError("always fail"))
        with patch.object(time, "sleep"):
            _run_with_retry(func)  # should not raise
        assert func.call_count == MAX_RETRIES

    def test_exponential_backoff_delays(self):
        func = MagicMock(side_effect=[RuntimeError("1"), RuntimeError("2"), None])
        with patch.object(time, "sleep") as mock_sleep:
            _run_with_retry(func)
        # 第 1 次失敗後等 2s，第 2 次失敗後等 4s
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(4)

    def test_keyboard_interrupt_propagates(self):
        func = MagicMock(side_effect=KeyboardInterrupt)
        try:
            _run_with_retry(func)
            assert False, "KeyboardInterrupt should propagate"
        except KeyboardInterrupt:
            pass
