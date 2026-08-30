"""
MiMo LLM Module - Xiaomi MiMo v2.5 API Integration
"""
import requests
import json
from config import MIMO_API_KEY, MIMO_API_URL, MIMO_MODEL
from llm.base import BaseLLM


class MiMoLLM(BaseLLM):
    def __init__(self):
        super().__init__()
        self.api_key = MIMO_API_KEY
        self.api_url = MIMO_API_URL
        self.model = MIMO_MODEL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _build_payload(self, messages, tools=None, stream=False):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 400
        }
        if tools:
            payload["tools"] = tools
        if stream:
            payload["stream"] = True
        return payload

    def _chat_raw(self, messages, tools=None):
        """Raw API call returning full response dict"""
        payload = self._build_payload(messages, tools=tools)
        try:
            response = requests.post(
                self.api_url, headers=self.headers,
                json=payload, timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]
        except requests.exceptions.RequestException as e:
            return {"content": f"API调用失败: {e}", "tool_calls": None}
        except (KeyError, IndexError) as e:
            return {"content": f"API响应格式错误: {e}", "tool_calls": None}

    def chat(self, user_input, history=None):
        """Simple chat: send input, get text response"""
        messages = self._build_messages(user_input, history)
        resp = self._chat_raw(messages)
        return resp.get("content") or ""

    def _build_messages(self, user_input, history):
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        if user_input:
            messages.append({"role": "user", "content": user_input})
        return messages

    def chat_stream(self, user_input, history=None):
        """Stream chat response from MiMo API"""
        messages = self._build_messages(user_input, history)
        payload = self._build_payload(messages, stream=True)

        try:
            response = requests.post(
                self.api_url, headers=self.headers,
                json=payload, stream=True, timeout=30
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content')
                                if isinstance(content, str) and content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
        except requests.exceptions.RequestException as e:
            yield f"API调用失败: {str(e)}"


# Test function
if __name__ == "__main__":
    llm = MiMoLLM()
    print("Testing MiMo API...")
    response = llm.chat("你好，请介绍一下自己")
    print(f"Response: {response}")
