import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import httpx  # noqa: E402

import gnani  # noqa: E402


class FakeResp:
    def __init__(self, status, text="", content=b""):
        self.status_code, self.text, self.content = status, text, content

    def json(self):
        return {"transcript": "ok"}


class TestRetries(unittest.TestCase):
    def setUp(self):
        self.real_post, self.real_backoff = gnani._client.post, gnani.BACKOFF
        gnani.BACKOFF = 0
        gnani.headers = lambda: {"X-API-Key-ID": "test"}

    def tearDown(self):
        gnani._client.post, gnani.BACKOFF = self.real_post, self.real_backoff

    def script(self, outcomes):
        calls = []

        def post(*a, **k):
            calls.append(1)
            o = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
            if isinstance(o, Exception):
                raise o
            return o
        gnani._client.post = post
        return calls

    def test_timeout_then_success(self):
        calls = self.script([httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow"), FakeResp(200)])
        self.assertEqual(gnani.stt(b"x", "hi-IN"), "ok")
        self.assertEqual(len(calls), 3)

    def test_server_error_is_retried(self):
        calls = self.script([FakeResp(503, "busy"), FakeResp(200)])
        self.assertEqual(gnani.stt(b"x", "hi-IN"), "ok")
        self.assertEqual(len(calls), 2)

    def test_gives_up_with_api_error(self):
        calls = self.script([httpx.ConnectError("down")])
        with self.assertRaises(gnani.ApiError) as cm:
            gnani.stt(b"x", "hi-IN")
        self.assertIn("gave up", str(cm.exception))
        self.assertEqual(len(calls), gnani.RETRIES)

    def test_rate_limit_is_waited_out_and_retried(self):
        old = gnani.RATE_WAIT
        gnani.RATE_WAIT = 0
        try:
            calls = self.script([FakeResp(429, "Only 1 active request is allowed at a time"), FakeResp(429, "again"), FakeResp(200)])
            self.assertEqual(gnani.stt(b"x", "hi-IN"), "ok")
            self.assertEqual(len(calls), 3)
        finally:
            gnani.RATE_WAIT = old

    def test_rate_limit_that_never_clears_is_an_error(self):
        old = gnani.RATE_WAIT
        gnani.RATE_WAIT = 0
        try:
            calls = self.script([FakeResp(429, "busy")])
            with self.assertRaises(gnani.ApiError) as cm:
                gnani.stt(b"x", "hi-IN")
            self.assertEqual(cm.exception.status, 429)
            self.assertEqual(len(calls), gnani.RATE_RETRIES + 1)
        finally:
            gnani.RATE_WAIT = old

    def test_only_one_request_is_in_flight_at_a_time(self):
        import threading
        import time
        active, peak, lock = [0], [0], threading.Lock()

        def post(*a, **k):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.03)
            with lock:
                active[0] -= 1
            return FakeResp(200)
        gnani._client.post = post
        ts = [threading.Thread(target=gnani.stt, args=(b"x", "hi-IN")) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(peak[0], 1)

    def test_client_errors_are_not_retried(self):
        calls = self.script([FakeResp(401, "bad key")])
        with self.assertRaises(gnani.ApiError) as cm:
            gnani.stt(b"x", "hi-IN")
        self.assertEqual(cm.exception.status, 401)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
