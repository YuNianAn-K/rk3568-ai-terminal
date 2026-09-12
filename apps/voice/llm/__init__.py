from llm.base import BaseLLM


def create_llm():
    """Factory function: create LLM adapter based on config"""
    from config import LLM_ENGINE
    if LLM_ENGINE == "glm":
        from llm.glm import GLMLLM
        return GLMLLM()
    if LLM_ENGINE == "mimo":
        from llm.mimo import MiMoLLM
        return MiMoLLM()
    raise ValueError("Unknown LLM provider")
