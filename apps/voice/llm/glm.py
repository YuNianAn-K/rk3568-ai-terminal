"""
GLM-4-Flash LLM Module - Zhipu AI GLM-4-Flash API Integration
OpenAI-compatible format with native function calling support
"""
import json
import requests
from config import GLM_API_KEY, GLM_API_URL, GLM_MODEL
from llm.base import BaseLLM


class GLMLLM(BaseLLM):
    def __init__(self):
        super().__init__()
        self.api_key = GLM_API_KEY
        self.api_url = GLM_API_URL
        self.model = GLM_MODEL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _chat_raw(self, messages, tools=None):
        """Raw API call returning full response dict"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 400
        }
        if tools:
            payload["tools"] = tools

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
        """Stream chat response from GLM API (OpenAI-compatible SSE)"""
        messages = self._build_messages(user_input, history)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 400,
            "stream": True
        }

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
    llm = GLMLLM()
    print("Testing GLM-4-Flash API...")
    response = llm.chat("你好，请介绍一下自己")
    print(f"Response: {response}")
