"""集中式配置：加载 .env 到环境变量，运行时动态读取，密钥绝不硬编码。

- 项目根目录的 .env 在导入本模块时加载一次（不覆盖已存在的环境变量）。
- 所有配置通过 settings.xxx 属性访问，每次访问都实时读取 os.environ，
  因此兼容测试中对环境变量的 monkeypatch 与真实环境的动态切换。
- 密钥（API Key / Token）只存在于 .env 或环境变量，绝不写进源码。
"""
import os
from pathlib import Path

# 本文件位于 python_service/，项目根目录是其上一级。
_ENV_FILE = Path(__file__).resolve().parent.parent / '.env'

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv 为可选依赖，缺失时仅失去 .env 文件加载能力
    load_dotenv = None

if load_dotenv is not None and _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)  # 真实环境变量优先于 .env 文件


class Settings:
    """动态读取环境变量的集中式配置门面。"""

    @property
    def agent_mode(self) -> str:
        return os.getenv('AGENT_MODE', 'auto')

    @property
    def openai_api_key(self) -> str:
        return os.getenv('OPENAI_API_KEY', '')

    @property
    def openai_base_url(self) -> str:
        return os.getenv('OPENAI_BASE_URL', '')

    @property
    def openai_model(self) -> str:
        return os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

    @property
    def judge_model(self) -> str:
        return os.getenv('JUDGE_MODEL', '')

    @property
    def gateway_token(self) -> str:
        return os.getenv('GATEWAY_TOKEN', '')

    @property
    def app_env(self) -> str:
        return os.getenv('APP_ENV', 'demo')

    @property
    def redis_url(self) -> str:
        return os.getenv('REDIS_URL', '')

    @property
    def rag_backend(self) -> str:
        return os.getenv('RAG_BACKEND', 'mock')

    @property
    def tavily_api_key(self) -> str:
        return os.getenv('TAVILY_API_KEY', '')


settings = Settings()
