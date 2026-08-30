"""
Baidu Speech Recognition Module
"""
import os
import json
import time
import requests


class BaiduASR:
    """百度语音识别"""

    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    ASR_URL = "https://vop.baidu.com/server_api"

    def __init__(self, api_key: str = None, secret_key: str = None):
        from config import BAIDU_API_KEY, BAIDU_SECRET_KEY
        self.api_key = api_key or BAIDU_API_KEY
        self.secret_key = secret_key or BAIDU_SECRET_KEY
        self.access_token = None
        self.token_expire = 0

    def _get_access_token(self) -> str:
        """获取百度 access_token，自动缓存和续期"""
        if self.access_token and time.time() < self.token_expire:
            return self.access_token

        resp = requests.post(self.TOKEN_URL, params={
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.token_expire = time.time() + data.get("expires_in", 2592000) - 60
        return self.access_token

    def recognize(self, audio_file: str, retries: int = 3) -> str:
        """
        识别 WAV 文件中的语音

        Args:
            audio_file: WAV 文件路径（16kHz, 16bit, mono）
            retries: 重试次数

        Returns:
            识别出的文字，失败返回空字符串
        """
        try:
            with open(audio_file, "rb") as f:
                audio_data = f.read()
        except OSError as e:
            print(f"ASR audio read failed: {type(e).__name__}")
            return ""

        for attempt in range(retries):
            try:
                token = self._get_access_token()
                resp = requests.post(
                    f"{self.ASR_URL}?cuid=ai_voice&token={token}&dev_pid=1537",
                    headers={"Content-Type": "audio/wav;rate=16000"},
                    data=audio_data,
                    timeout=15,
                )
                resp.raise_for_status()
                result = resp.json()

                if result.get("err_no") == 0:
                    return "".join(result.get("result", []))
                elif result.get("err_no") == 110:
                    self.access_token = None
                    token = self._get_access_token()
                    continue
                else:
                    print(f"ASR error: {result.get('err_msg', 'unknown')}")
                    return ""

            except (requests.exceptions.RequestException, ValueError, KeyError) as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                # Do not print the exception message because requests may include
                # the access token embedded in the request URL.
                print(f"ASR request failed: {type(e).__name__}")
                return ""

        return ""


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python baidu_asr.py <audio_file>")
        sys.exit(1)
    asr = BaiduASR()
    text = asr.recognize(sys.argv[1])
    print(f"Result: {text}")
