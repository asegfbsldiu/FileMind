"""Supported OpenAI-compatible provider defaults."""

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ProviderPreset:
    """Public default connection values for one chat-completions provider."""

    provider_id: str
    name: str
    base_url: str
    model: str
    note: str
    kind: str = "openai"
    requires_key: bool = True
    api_key_env: str = ""
    local: bool = False


PROVIDERS: tuple[ProviderPreset, ...] = (
    ProviderPreset("deepseek", "DeepSeek", "https://api.deepseek.com", "deepseek-flash",
                   "官方当前通用模型 DeepSeek-V4.1-Flash；模型 ID 为 deepseek-flash，兼容 Chat Completions。"),
    ProviderPreset("openai", "OpenAI", "https://api.openai.com/v1", "gpt-5-mini",
                   "使用 OpenAI Chat Completions；需单独开通 API 计费与权限。"),
    ProviderPreset("siliconflow", "硅基流动 SiliconFlow", "https://api.siliconflow.cn/v1",
                   "deepseek-ai/DeepSeek-V4-Flash", "模型可用性和名称以 SiliconFlow 模型广场为准。"),
    ProviderPreset("dashscope", "阿里云百炼 DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1",
                   "qwen-plus", "预设北京公共兼容端点；地域、业务空间和模型授权可能影响可用性。"),
    ProviderPreset("zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "",
                   "OpenAI 兼容接口；请填写账户实际可用的模型 ID。"),
    ProviderPreset("wenxin", "百度千帆 ERNIE", "https://qianfan.baidubce.com/v2", "",
                   "千帆 V2 兼容接口；请填写账户实际可用的模型 ID。"),
    ProviderPreset("kimi", "Kimi 月之暗面", "https://api.moonshot.cn/v1", "",
                   "Moonshot 兼容接口；请填写账户实际可用的模型 ID。"),
    ProviderPreset("doubao", "豆包 Doubao", "https://ark.cn-beijing.volces.com/api/v3", "",
                   "火山方舟兼容接口；请填写模型 ID 或推理接入点 ID。"),
    ProviderPreset("volcengine", "火山引擎", "https://ark.cn-beijing.volces.com/api/v3", "",
                   "火山方舟兼容接口；模型、接入点和区域以控制台为准。"),
    ProviderPreset("qwen", "千问 Qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "",
                   "百炼北京兼容接口；请按账户与区域填写模型 ID。"),
    ProviderPreset("hunyuan", "腾讯混元 Hunyuan", "https://api.hunyuan.cloud.tencent.com/v1", "",
                   "混元兼容接口；请填写账户实际可用的模型 ID。"),
    ProviderPreset("ollama", "本地 Ollama", "http://localhost:11434/v1", "llama3.2",
                   "连接本机 Ollama；llama3.2 只是示例，请检测并选择已安装的非云端模型。",
                   kind="ollama", requires_key=False, local=True),
    ProviderPreset("custom", "自定义 OpenAI 兼容接口", "", "", "仅支持兼容的 Chat Completions 接口。"),
)

PROVIDER_BY_ID = {provider.provider_id: provider for provider in PROVIDERS}
ENVIRONMENT_KEY_NAMES = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "custom": "FILEMIND_API_KEY",
    "zhipu": "ZHIPU_API_KEY", "wenxin": "WENXIN_API_KEY", "kimi": "MOONSHOT_API_KEY",
    "doubao": "DOUBAO_API_KEY", "volcengine": "VOLCENGINE_API_KEY", "qwen": "QWEN_API_KEY",
    "hunyuan": "HUNYUAN_API_KEY", "ollama": "OLLAMA_API_KEY",
}


def is_local_connection(provider_id: str, base_url: str) -> bool:
    """Recognize only loopback Ollama endpoints as local, never a remote URL."""
    parsed = urlsplit(base_url.strip())
    return (provider_id == "ollama" and parsed.scheme in {"http", "https"}
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and not (parsed.username or parsed.password or parsed.query or parsed.fragment))


PROVIDER_MODEL_SUGGESTIONS = {provider.provider_id: (provider.model,) if provider.model else ()
                              for provider in PROVIDERS}
