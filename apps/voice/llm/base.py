"""
Base LLM Module - Abstract base class for LLM adapters with function calling support
"""
import json
from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """Base class for LLM adapters"""

    def __init__(self):
        self.system_prompt = "你是语音助手，请用一句简洁自然的口语回答，控制在50字以内，不要使用表情符号。"

    @abstractmethod
    def chat(self, user_input: str, history: list = None) -> str:
        """Simple chat: send input, get text response. Backward compatible."""
        pass

    def chat_stream(self, user_input: str, history: list = None):
        """
        Stream chat response token by token. Default fallback: yield the full blocking response.
        Subclasses should override with real SSE streaming for better latency.
        """
        yield self.chat(user_input, history)

    @abstractmethod
    def _chat_raw(self, messages: list, tools: list = None) -> dict:
        """
        Raw API call with full response.

        Returns dict with keys from the API response message:
            - "content": str or None
            - "tool_calls": list or None
        """
        pass

    def chat_with_tools(self, user_input: str, history: list = None,
                        tools_schema: list = None, tool_executor=None,
                        max_rounds: int = 5) -> str:
        """
        Function calling loop: LLM decides tool calls, program executes,
        results go back to LLM. Max max_rounds iterations to prevent loops.

        Returns final text response.
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        for _ in range(max_rounds):
            resp = self._chat_raw(messages, tools=tools_schema)

            content = resp.get("content")
            tool_calls = resp.get("tool_calls")

            if content and not tool_calls:
                return content

            if not tool_calls:
                return content or "抱歉，我没有理解你的问题"

            # Append assistant message with tool_calls to history
            messages.append(resp)

            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "")
                args_str = func.get("arguments", "{}")
                try:
                    arguments = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    arguments = {}

                print(f"  [Tool] {name}({arguments})", flush=True)
                try:
                    result_str = tool_executor(name, arguments)
                except Exception as e:
                    result_str = f"工具执行失败: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result_str
                })

        return "工具调用轮次过多，请简化问题后重试"
