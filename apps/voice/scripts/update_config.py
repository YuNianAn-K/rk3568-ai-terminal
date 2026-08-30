#!/usr/bin/env python3
"""Add environment-based GLM config to config.py if not already present."""
import sys


config_path = "/root/AI_voice/config/config.py"

with open(config_path, "r", encoding="utf-8") as handle:
    content = handle.read()

if "LLM_ENGINE" in content:
    print("LLM_ENGINE already exists in config.py, skipping")
    sys.exit(0)

glm_block = '''# LLM Engine Selection
LLM_ENGINE = "glm"  # Options: "mimo", "glm"

# GLM Configuration (credential comes from the process environment)
GLM_API_KEY = os.getenv("GLM_API_KEY", "")
GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MODEL = "glm-4.7-flash"

'''

content = content.replace(
    "# MiMo API Configuration",
    glm_block + "# MiMo API Configuration",
)

with open(config_path, "w", encoding="utf-8") as handle:
    handle.write(content)

print("config.py updated successfully")
