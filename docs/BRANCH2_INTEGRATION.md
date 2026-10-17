# branch2 功能整合记录

日期：2026-10-17。来源：同级 `branch2/FileMind-main`，MIT 许可证，与现有项目版权声明一致。来源目录没有 `.git` 元数据，不能确认它对应的提交号；本次依据源码逐模块移植，没有用旧 README 的功能或测试数字代替检查。

## 实际整合

| 模块 | 行为 |
| --- | --- |
| 多模型配置 | 添加、勾选、排序、删除模型，最多保存 20 个；配置和并行开关原子保存；清空列表后不会自行恢复默认项 |
| Orbit 并行问答 | 默认关闭；开启后使用 1–4 个模型，保持选择顺序，按模型和耗时分组；单项失败不抹掉其他回答，全部失败可重试 |
| 请求边界 | 保留 Orbit 系统提示词、最近 20 条与 60,000 字符上下文限制；并行发送前列出真实端点确认；附件明确要求关闭并行再发送 |
| 取消与会话 | 复用现有 worker 身份、取消和会话 ID 检查；取消后的返回不写入历史或覆盖新会话；重试不重复保存用户消息 |
| 密钥兼容 | 只持久化模型非密钥字段；保留 Windows 凭据优先级；接口地址不同不会自动复用原接口密钥；运行时配置的 repr 隐藏密钥 |
| Ollama | 本机模型检测、无密钥配置、OpenAI 兼容调用；只接受回环地址；检测限制响应大小、禁用代理和跨地址重定向；本机服务可能自行使用云端模型，界面不承诺绝对离线 |
| 更多服务商 | 智谱、千帆、Kimi、豆包、火山引擎、千问、混元快捷入口；新云端入口不采用来源中可能过时的模型示例，模型 ID 留给用户按账户填写 |
| 模型切换 | 使用现有圆角选择器选择当前服务商保存的模型，立即用于后续请求；只更新模型字段，不重新保存或删除 API Key |
| 建议解析 | 新增逐行解析入口；缺少可选字段可采用安全默认值，无效行单独标记，重复 ID 行不采纳；保留原严格解析 API 和路径/字段检查 |
| 改名 | AI、手工编辑与计划构建共用完整且大小写不敏感的扩展名链；保留编辑原子性，拒绝 `.tar.gz` → `.gz` |
| 视觉 | 多模型管理沿用浅紫卡片和统一 QSS，编辑型模型下拉只保留外层边界；保留现有聊天头像、动画、中文输入法处理和圆角弹层 |

分组回答有明确的本地长度上限；超限时标注截断，避免多个长回答超过会话存储上限而全部保存失败。并行问答当前等待整组有界请求结束后展示结果；新增流式协议接口供适配器使用，没有宣称聊天页已改成流式输出。

## 避免冲突的处理

- 保留当前 `filemind/models/` 包与兼容导出，不放入来源中的同名 `models.py`。
- 保留按日预设、200 段会话容量、最近对话搜索、时间/数量、圆角删除菜单、动态头像、减少动态效果和侧栏自适应。
- 保留已授权内容识别、转换清除、字体/EPUB 等新增转换；没有复制来源中较早的转换文件覆盖它们。
- 第一轮未整合主题和导航；随后按用户要求补齐独立“模型配置”、头像菜单中的通用设置、五种外观和全部服务商图片。保留现有布局与圆角弹层，具体见 [第七轮整合记录](ROUND7_MODEL_SETTINGS_THEMES.md)。
- 来源的建议解析允许更多字段/类型；这里只采用逐行容错思路，额外路径、命令和不合法字段仍被拒绝。
- 不采用来源中去掉路径前导斜杠、延后编辑校验、只统计排除行、移除执行器 `review_note` 检查的差异，保留当前更严格的本地校验。
- 不采用写死队友桌面绝对路径的 `FileMind.spec`、`FileMind-Setup.spec`；它们也引用了来源目录中未提供的安装器脚本。本轮没有产出安装包。
- 没有运行 Git merge/reset、覆盖工作区、读取真实 `.env`/凭据、迁移聊天数据，或操作用户真实整理目录。

## 修改文件

新增：

- `filemind/ai/model_config.py`、`chat_result.py`、`adapters.py`、`multi_model.py`：从队友代码移植并修正兼容、安全与取消边界。
- `filemind/ui/widgets/model_selector.py`：模型管理，适配现有弹层、纯文本标签与主题。
- `filemind/ui/styles/models.qss`：模型管理卡片及编辑框样式。
- `tests/test_model_config.py`、`test_multi_model.py`、`test_multi_model_settings.py`、`test_model_selector.py`：移植的相关回归。
- `tests/test_branch2_compatibility.py`、`test_branch2_protocol.py`：当前实现的兼容、取消、隐私、密钥和协议回归。

修改：

- `filemind/ai/providers.py`、`openai_compatible.py`、`response.py`：服务商元信息、独立完成/流式协议与逐项建议解析。
- `filemind/storage/settings.py`：兼容旧 profile 的模型列表与模型选项保存、按地址绑定密钥。
- `filemind/core/planner.py`、`plan_editor.py`：共用扩展名规则，保留其他安全检查。
- `filemind/ui/main_window.py`：请求调度、批量确认、重试、检测及当前模型同步。
- `filemind/ui/pages/settings_page.py`：新增管理卡片和检测，保留现有表单、锁屏、隐私与密钥错误遮蔽。
- `filemind/ui/pages/assistant_page.py`：修复欢迎页错误提示不可见。
- `filemind/ui/widgets/chat_input.py`：现有模型选择器接入真实已保存选项，提示并行发送范围。
- `filemind/ui/styles/theme.py`：加载新增 QSS。
- `tools/review_ui.py`：新增模型密钥解析仍使用隔离凭据，不读取真实环境变量密钥。
- `README.md`、本文：功能说明与验收记录。

第一轮功能整合没有改变技术栈、运行依赖和构建配置；当时的源码备份确认这些文件未被替换。后续第七轮仅为新增图片补充 `pyproject.toml` 的资源打包规则，运行依赖不变，见第七轮记录。

备份与差异索引仅含源码及非秘密工程声明，保存在 Git 忽略的 `.artifacts/branch2-integration/before/`、`diffs/`、`inventory.json`、`changed.json`；不是用户数据备份。

## 验证

遵循用户要求，只运行新功能及受影响模块，没有重复跑稳定的全部转换测试。

1. 模型/存储/已有设置与聊天服务：32 passed、5 subtests passed，7.60 秒。
2. 中间组合回归发现分组回答缺少耗时显示，已修正；首页错误不可见也在兼容用例中复现并修正，没有删除或降低断言。
3. 受影响组合：103 passed、17 subtests passed，40.40 秒。命令：

```powershell
py -3.13 -m pytest tests/test_branch2_protocol.py tests/test_model_config.py tests/test_multi_model.py tests/test_multi_model_settings.py tests/test_model_selector.py tests/test_branch2_compatibility.py tests/test_configuration_flow.py tests/test_ai_response.py tests/test_ai_service.py tests/test_plan_editor.py tests/test_content_organization.py tests/test_recent_sessions.py -q --tb=short
```

4. 最后修正与样式调整后的定向复查：30 passed、5 subtests passed，9.43 秒。

```powershell
py -3.13 -m pytest tests/test_branch2_protocol.py tests/test_branch2_compatibility.py tests/test_model_config.py tests/test_model_selector.py -q --tb=short
```

5. `py -3.13 -m compileall -q main.py filemind tests tools` 通过；Git 空白检查通过。本机未安装 pyflakes，本轮没有增加该依赖或宣称运行过 lint。
6. Windows 原生 Qt 启动：1024×700、1280×850。设置内容宽度/视口分别为 718/718、974/974，没有横向溢出。实际检查模型排序、启用、保存与重新读取、Ollama 隐藏密钥、圆角模型选择、即时切换、Markdown 分组、拒绝发送确认，以及全部现有页面导航。
7. 本机回环 HTTP 测试服务器实际验证 `/api/tags`、`/v1/chat/completions` 路径、系统消息和 JSON 协议；这是测试服务器，不是实际 Ollama 或模型回答。
8. 实际探测 `http://127.0.0.1:11434/api/tags` 返回连接失败，PATH 中也没有找到 Ollama；不能宣称本机已安装或连接成功。没有向真实云端模型发送请求，也没有读取真实 API Key。

截图和原生脚本：`.artifacts/branch2-integration/check_ui.py`、`settings-1024.png`、`model-manager-1024.png`、`model-manager-1280.png`、`ollama-settings.png`、`orbit-model-popup.png`、`grouped-chat.png`、`parallel-consent.png`。全部使用明确标记的临时生成内容，不代表真实模型输出。

## 端点参考与使用步骤

本轮核对了 [Ollama 模型检测](https://docs.ollama.com/api/tags) 和 [OpenAI 兼容协议](https://docs.ollama.com/api/openai-compatibility)。该官方说明也指出，本机 Ollama 服务可以转发到云端模型，因此界面保留相应范围说明。

新增云端端点参考：[智谱官方示例](https://docs.bigmodel.cn/cn/best-practice/case/ai-search-engine)、[千帆 V2](https://ai.baidu.com/ai-doc/WENXINWORKSHOP/2m3fihw8s)、[火山方舟](https://docs.volcengine.com/docs/ark/context-management?lang=en)、[混元 OpenAI 兼容文档](https://main.qcloudimg.com/raw/document/product/pdf/1729_111006_cn.pdf)。Kimi 页面本次浏览未成功返回内容，预设来自队友配置，不当作本次已验证的账户可用性。

使用时先在原有服务商表单保存地址、真实模型 ID 和自己的密钥，再向模型列表添加条目。选择开启并行、保存后，在 Orbit 输入消息并确认目标接口。使用 Ollama 时需自行安装并启动服务、下载模型，再点击检测选择；FileMind 不自动安装或下载模型。
