"""
MiMo LLM Module - Xiaomi MiMo v2.5 API Integration
"""
from mimo_http import MiMoError, MiMoHTTP, first_choice
from config import MIMO_API_KEY, MIMO_API_URL, MIMO_MODEL
from llm.base import BaseLLM


class MiMoLLM(BaseLLM):
    def __init__(self):
        super().__init__()
        self.api_key = MIMO_API_KEY
        self.api_url = MIMO_API_URL
        self.model = MIMO_MODEL
        self.http = MiMoHTTP(api_key=self.api_key, url=self.api_url)

    def _build_payload(self, messages, tools=None, stream=False):
        from config import MIMO_THINKING
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 400,
            "thinking": {"type": MIMO_THINKING},
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
            choice = first_choice(self.http.request(payload), allow_tools=bool(tools))
            message = choice.get("message")
            if not isinstance(message, dict):
                raise MiMoError("invalid_response")
            return message
        except MiMoError as error:
            return {"content": "API调用失败: " + str(error), "tool_calls": None}

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

        complete = False
        has_text = False
        events = self.http.responses(payload)
        try:
            for event in events:
                if event.get("_done"):
                    complete = True
                    break
                if event.get("choices") == [] and "usage" in event:
                    continue
                choice = first_choice(event)
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    raise MiMoError("invalid_stream")
                content = delta.get("content")
                if content is not None and not isinstance(content, str):
                    raise MiMoError("invalid_stream")
                if content:
                    has_text = True
                    yield content
                if choice.get("finish_reason") == "stop":
                    complete = True
            if not complete or not has_text:
                raise MiMoError("truncated_stream" if has_text else "empty_response")
        finally:
            events.close()

    def close(self):
        self.http.close()


# Test function
if __name__ == "__main__":
    llm = MiMoLLM()
    print("Testing MiMo API...")
    response = llm.chat("你好，请介绍一下自己")
    print(f"Response: {response}")
