# FileMind 文件整理助手

## Windows 发布打包

使用 **PyInstaller 文件夹版（onedir）+ Inno Setup 6.5+**。在克隆后的仓库根目录使用 PowerShell 执行：

```powershell
.\scripts\build-windows.ps1 -ValidateOnly
.\scripts\build-windows.ps1 -Stage Prepare
.\scripts\build-windows.ps1 -Stage Bundle
```

随后在 Inno Setup Compiler 打开 `packaging\FileMind.iss`，点击 Compile。编译成功后整理发布文件：

```powershell
.\.venv-build\Scripts\python.exe tools\windows_release.py artifacts
```

也可以执行 `.\scripts\build-windows.ps1 -Stage Installer` 完成命令行编译；编译器不在常见目录时，使用 `-IsccPath` 指定实际路径。最终文件位于 `dist/release/<版本>/`，安装包和便携 ZIP 通过 GitHub Releases 分发。

完整步骤、六步中文安装向导与 GitHub 草稿发布见 [正式 Windows 发布流程](docs/RELEASE_PIPELINE.md)。

FileMind 是一个 Python + PySide6 Windows 桌面文件整理工具。它可用本地规则分类，也可调用配置好的 OpenAI Chat Completions 兼容服务生成分类、相对目标子目录和可选改名建议。所有建议都要经过本地安全校验并由用户确认后，才会交给本地执行器。

## 当前功能

- 只扫描用户明确选择的目录第一层普通文件，不递归；默认扫描和分类不读取正文。另行启用内容识别并逐次确认后才读取有限片段或图片缩略图。
- 本地规则支持按文件类型或修改年月日分类（`YYYY-MM-DD`），可离线使用；课程/项目语义预设需要在线 AI，不会把本地规则结果显示成 AI 结果。
- 主工作区先显示导入文件清单，采用 Windows 关联图标与统一备用类型图标；规则区和文件区之间可上下拖动并记住高度。选择分类方式、输入规则后，点击发送或按 Enter 生成建议，Shift+Enter 换行、Tab 移到发送按钮。目标树和详情表支持联动核对，再单独打开预览确认执行。
- AI 可建议分类、分类下相对目录、理由和保留扩展名的可选新文件名；稳定文件 ID 用于关联结果，不使用模型行号。
- 大文件夹按文件数量和序列化长度分批请求；失败批次会显示在对应预览行，部分 AI 结果不会伪装为完整成功。
- 预览包含原路径、目标路径、原名、新名、分类、理由、建议来源和本地校验状态。可双击修改分类或新文件名，取消“执行”勾选以排除单个文件；修改后重新校验，目录树和主页面摘要同步更新。
- 目标冲突、已排除和未确认的 AI 失败行会逐项跳过，其余安全行可继续执行。历史记录分别显示成功、跳过、失败及原因；撤销只恢复实际成功移动的文件。
- AI 不能选择绝对路径、执行代码、Shell 命令或直接操作文件。核心计划器检查路径、文件名、重名、目标冲突和符号链接；执行器不覆盖文件，记录历史并支持撤销。
- 扫描、连接测试、AI 请求和文件操作在后台线程中进行。
- Orbit 是独立通用对话页面，支持本地会话、新建/切换/删除、Markdown 回答、快捷任务、停止与重试；聊天中显示 Orbit 头像和本机用户头像，用户消息采用浅蓝色气泡，统一 QSS 位于 `filemind/ui/styles/orbit.qss`。附件需用户明确选择并在发送前确认。
- 侧栏可通过顶部按钮或 `Ctrl+B` 收起/展开，可拖动分隔线调整至 230–380px，宽度和收起状态会保存在本机。
- Orbit 最近对话独立滚动，显示标题、活动时间与消息数，可按标题搜索；保留最近 200 段，不按天清除。删除菜单复用模型选择器的圆角弹层，删除前仍需确认。
- 独立格式转换页包含 QSS 彩色能力卡片、加粗标题与逗号分隔的格式列表：图片、文本/电子书、PDF、Office 文字导出、音视频、字体容器及单文件 ZIP。编码器在后台检测，目标下拉框以实际输入文件为准；× 只清除选择，不删除文件。
- Orbit 附件第一版支持 PNG/JPEG/GIF/WebP 图片（仅 DeepSeek V4.1 Flash 已核验图像输入）及 UTF-8 文本/代码文件；单个附件上限 4 MB，每次最多 5 个、总量 12 MB。PDF、Office 文档和多模态模型自动探测尚未实现。

## 按内容分类与命名

按修改年月日、本地文件类型分类都不会理解文件内容或自动改名。想为哈希图片名、编号文档生成描述性名称时：

1. 选择目录并读取文件列表，移走不想发送的文件。
2. 选择“按内容分类与命名 · AI”，检查规则，并保持“应用 AI 改名”勾选。
3. 点击“识别内容并生成建议”，确认本次数据发送范围。内容识别默认关闭，每次请求都重新确认。
4. 查看目标目录树、建议新名称和理由；可逐条编辑或取消执行，再预览并明确确认整理。

本版支持 UTF-8 / 带 BOM 的 UTF-16 文本与代码、PDF 文本层、DOCX/XLSX/PPTX 文本，以及单帧图片。文档最多发送开头 1800 字（PDF 只看前三页），图片去掉 EXIF 后等比压缩到最长 1024 像素。每次最多 128 个文件，单文件 8 MB，图片请求数据合计最多 12 MB。图片协议目前仅依据官方文档启用 DeepSeek `deepseek-flash`，不把其他模型默认视为支持视觉；不是对真实 API 调用成功的保证。

疑似 `.env`、密钥、密码、私钥等凭据文件在读取前排除，正文中的部分常见凭据模式会遮蔽；这不能保证消除文档或图片中的所有个人信息。超限、损坏、不支持和失败文件会明确标记，执行时跳过，不静默回退成 AI 成功。片段只在当前任务内存中使用，不存入操作历史。Orbit 会话、附件确认和提示词仍独立。

## 安装与启动

使用 Python 3.13；当前界面与本机锁屏在 Windows 下验证。安装界面、AI 与本地转换依赖：

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 main.py
```

也可执行 `py -3.13 -m pip install -e .` 安装后使用 `filemind` 启动；该入口同样先经过本机锁屏。版本号取自 `filemind.__version__`，依赖仍以 `requirements.txt` 为唯一清单，安装包包含 QSS、SVG 与品牌图片。

Windows 的配置和数据目录保持 `%APPDATA%/FileMind` 与 `%LOCALAPPDATA%/FileMind`；macOS 使用 `~/Library/Application Support/FileMind`，Linux 遵循 `XDG_CONFIG_HOME` / `XDG_DATA_HOME`。非 Windows 系统不提供 Windows 凭据管理器和 DPAPI 记住解锁；需要自行配置环境变量或明确选择本机密钥文件。原有 macOS 旧路径不自动迁移。

## 本机密码与锁屏

首次从 `main.py` 启动时设置本机密码（至少 8 个字符），并保存一次性显示的恢复码。下次启动使用密码解锁后才会加载工作区。左下角本机用户菜单、设置页的“本机工作空间”可手动锁定或修改密码；快捷键是 `Ctrl+L`。运行中的文件/API 任务需先完成或停止，再锁定。

密码不以明文保存：应用使用 16 字节随机盐、600,000 次 PBKDF2-HMAC-SHA256 和常量时间比较。验证值位于 `%LOCALAPPDATA%/FileMind/lock/auth.json`，写入前限制文件为当前用户访问，采用原子替换。连续五次失败会等待 30 秒。

“记住解锁 7 天”保存 Windows DPAPI 保护的随机令牌，不保存密码，也不使用 API Key 的凭据存储；令牌到期、手动锁定和修改密码都会使其失效。忘记密码可在解锁页输入恢复码重设，新恢复码会替代旧码；文件、聊天和模型设置保留。密码和恢复码都遗失时，没有应用内绕过入口，请勿删除其他配置或数据。锁屏是应用级访问提示，不等同于 Windows 账户安全、文件加密或防止本机管理员修改程序。

左下角用户菜单可“修改用户名”、更换本机头像或“锁定 / 登出”。用户名支持 1–32 个字符，保存后同步到侧栏与聊天中的用户名称，重启后保留；长名称在侧栏省略显示，悬停可查看完整名称。名称仅在本机显示，不加入模型请求，也不改写已有聊天记录。头像仅接受用户主动选择的 PNG/JPEG/WebP/BMP，最大 8 MB、1600 万像素，保存为去除原始元数据的 128×128 PNG，不上传、不写入聊天历史。用户名、头像和侧栏偏好位于 `%LOCALAPPDATA%/FileMind/` 的 `avatar.png`、`workspace.json`，不涉及模型密钥配置。

## 本地格式转换

在侧栏打开“格式转换”，选择或拖入一个文件，等待识别后选择目标，点击“开始转换并保存…”，指定一个尚不存在的输出文件。源文件保留，已有输出不会覆盖；可以取消尚未发布的任务。编码期间取消会在安全停止点生效，结果发布完成后会如实显示成功。

| 输入 | 真实实现 | 限制 |
| --- | --- | --- |
| PNG, JPEG, WebP, TIFF, BMP, GIF, AVIF, ICO, TGA, PCX, PPM 等单帧图片 | 本机 Pillow 已安装的 PNG, JPEG, WebP, TIFF, BMP, GIF, AVIF, ICO, TGA, PCX, PPM, 单页 PDF | ICO 等比留白；拒绝动图、多页输入；有损编码和 GIF 调色板影响画质；无 RAW/HEIC |
| TXT/Markdown/代码/日志/HTML/XML/YAML 等 | UTF-8/UTF-16、静态 HTML、DOCX；HTML 提取纯文本、XML 格式化 | 输入限 UTF-8 或带 BOM 的 UTF-16；不执行脚本、不加载外部资源；文本到 DOCX 不复刻复杂排版 |
| CSV / JSON / YAML | CSV ↔ JSON、CSV → XLSX、JSON ↔ YAML | XLSX 写入按字符串；拒绝重复表头、嵌套 CSV、YAML 别名及 JSON 不可表达的值 |
| 文本 / EPUB | 文本创建含目录的 EPUB 3；EPUB 按阅读顺序提取章节文字 | 不处理 DRM、不读取外链；创建时按文本段落排版，不复刻原版面 |
| PDF | 文本层 TXT, DOCX, 静态 HTML；全部页面 PNG/JPEG ZIP | 最多 100 页；DOCX/HTML 仅重建文本，不保留原排版、表格结构和图片；无 OCR |
| DOCX / PPTX | 段落、表格或幻灯片文字导出 TXT/静态 HTML | 不保留版面、图片和动画，PPTX 不导出讲者备注 |
| XLSX | 全部工作表值导出 JSON 或多 CSV ZIP | 公式仅使用文件缓存值，不执行公式；每表 5 万行/200 列、全工作簿 50 万单元格 |
| 音视频 | 本机编码器可用的 MP3, WAV, FLAC, OGG, AAC, M4A, OPUS, WMA；MP4, WebM, MKV, MOV，或提取首条音轨 | 固定本地编码参数；不保证字幕、封面、多轨和原始元数据保留；重新编码可能有损 |
| TTF, OTF, WOFF, WOFF2 字体 | TTF/OTF → WOFF/WOFF2；WOFF/WOFF2 → 原始字形类型的 TTF 或 OTF | fontTools + Brotli；不做 TTF/CFF 轮廓互转，不修改字体授权；单文件 16 MB，展开后 64 MB |
| DOC/DOCX、XLS/XLSX、PPT/PPTX、ODT/ODS/ODP、RTF | 检测到 LibreOffice 后才提供实验性排版转换 | 当前验收环境未安装 LibreOffice，未实测此适配器；WPS/ET/DPS 专有格式不宣称支持 |
| 任意普通文件 | 单文件 ZIP 打包 | 不递归文件夹、不解压，源文件保持不变 |

单个输入最大 64 MB，文本转换最大 8 MB，图片最大 3200 万像素，PDF 单页渲染最多 2000 万像素。压缩文档不展开到磁盘，限制条目数量与展开量。转换先写入临时文件，重新检查源文件状态、取消和输出冲突后，再以不覆盖方式发布。FFmpeg 子进程可取消，最长执行 5 分钟；编码期间显示不确定进度，完成后显示结果，未伪造百分比。整个转换流程不调用 AI、不联网。

## 树状整理预览

独立预览展示目标根目录、蓝色文件夹、嵌套子目录和目标文件；图标、箭头与数量来自当前本地校验的计划，不会额外遍历文件夹。支持展开/折叠、名称/目标路径/理由搜索，以及选中目录或文件联动详情。目录按路径层级筛选，文件按精确路径筛选。完整名称与路径可以在提示和下方详情中查看、选取复制。

树中“待执行”表示尚未操作，表格“通过”表示本地校验通过。异常、重名冲突和已排除项会在节点及摘要中显示；空计划或全部行均不可执行时禁用执行。计划内重名会追加 `(2)`、`(3)`；已存在的磁盘目标不会覆盖，而是逐项跳过。之后仍需经过主窗口二次确认，执行器会再次校验。

## AI 服务配置

可直接点击左侧“设置”或按 Ctrl+, 编辑并保存配置，无需修改入口代码。保存后会明确显示“尚未验证连接”，用户已保存的服务商在重启后优先恢复。普通启动入口不会进入临时验收限制。

首次使用时默认选择 DeepSeek，Base URL 为 `https://api.deepseek.com`，模型 ID 为 `deepseek-flash`（官方显示名 DeepSeek-V4.1-Flash）。API Key 不预置；请在“设置”中填写自己的密钥。首次配置不会覆盖用户已保存的 provider profile。也可以选择 OpenAI、硅基流动、阿里云百炼或自定义兼容接口。可以修改 Base URL、模型名称、请求超时和 API Key。预设只提供建议值；模型是否对账户开放取决于服务商、区域和账户权限。兼容性以 Chat Completions 为目标，不支持只提供 Responses API 或专有请求格式的服务。

API Key 默认保存在 Windows Credential Manager；普通配置写入当前用户 `%APPDATA%/FileMind/settings.json`。切换服务商后需保存配置。环境变量可按 provider 设置：`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`SILICONFLOW_API_KEY`、`DASHSCOPE_API_KEY` 或 `FILEMIND_API_KEY`。密钥读取优先级为：Windows 凭据管理器 → 用户明确选择的本地密钥文件 → provider 环境变量 → 旧版项目 `.env` 中的 `DEEPSEEK_API_KEY`（仅 DeepSeek）。设置页会显示密钥来源；`.env.example` 仅为空占位，不会自动加载。

如果没有可用系统凭据存储，用户可显式勾选“本机配置文件明文保存”。该文件位于用户应用数据目录之外的 FileMind 配置目录，并尝试限制为当前用户访问；明文保存存在风险，不推荐开启。密钥不会写入普通设置、操作历史、源码或错误提示。

第一次生成在线 AI 预览前会询问授权。发送字段包括文件名、扩展名、大小、修改时间和用户规则；不会发送文件正文、整个文件夹或绝对路径。请求需要联网，在线 AI 不是离线功能。每次连接测试都会真实请求所选服务商，可能产生少量 token 费用；没有真实服务配置时不要把 mock 测试结果当作连接成功。

Orbit 首次发送消息前会单独询问授权。发送范围是你输入的消息与当前会话最近上下文，服务商由“设置”页当前已保存的配置决定。添加附件时，每次发送前还会列出文件名并再次确认；被选中文件的内容会发送给当前服务商。聊天记录保留附件文件名，不保留本地路径或附件正文；应用重启后如需重试含附件消息，需要重新选择附件。Orbit 不会自动访问本机文件或文件整理记录。会话保存在 `%APPDATA%/FileMind/chat_history.json`，不保存 API Key。模型切换并保存后，之后的新请求直接使用新配置，无需重启。

## branch2 整合：多模型与本机 Ollama

Windows EXE、Inno Setup 安装包及 GitHub Releases 的命令步骤见 [Windows 发布说明](docs/WINDOWS_RELEASE.md)。统一应用图标位于 `filemind/ui/assets/FileMind_AppIcon.ico`，Inno Setup 脚本位于 `packaging/FileMind.iss`。

左侧“模型配置”集中管理服务商、API 配置和并行模型，列表使用随应用打包的服务商图标。左下角“本机用户 → 设置”（或 `Ctrl+,`）打开通用设置：外观、锁屏、密码和隐私。外观提供浅色、深色、跟随系统、绿色、橙色，立即生效并自动保存。绿色和橙色使用浅色背景。

“模型配置”页新增多模型管理卡片，可添加、勾选、排序和移除模型，最多保存 20 个。并行模式默认关闭；开启并保存后，Orbit 将向 1–4 个启用模型分别发送当前问题、近期上下文与系统提示词，每次列出实际接口请求确认。回答按模型与耗时分组，一项失败不影响其他结果；全部失败仍可重试，取消后不会保存迟到回答。并行模式不发送附件，需要关闭后再单独确认附件发送。

模型列表只保存非密钥字段，继续复用现有服务商凭据。不同 Base URL 不会自动继承原接口密钥；请先在上方服务商配置中保存对应地址和密钥。Orbit 下拉可以直接切换当前服务商已保存的模型，后续请求立即生效，保留原有圆角弹层。

新增智谱、千帆、Kimi、豆包、火山引擎、千问、混元快捷入口；新云端入口不预填未经核验的模型名称，需要填写账户实际可用的模型 ID。Ollama 可检测本机已安装模型，不要求 API Key；示例模型不代表已经安装。仅允许回环地址，远程部署请使用自定义兼容接口。本机服务可能自行调用云端模型，请核对 Ollama 配置。

AI 建议现在按行隔离格式或路径错误，有效建议可继续进入预览；异常行仍标记失败并跳过。手工与 AI 改名共用完整扩展名链校验，例如 `.tar.gz` 不能改成 `.gz`。

本轮整合范围、未采用的冲突改动及定向验收结果见 [branch2 整合记录](docs/BRANCH2_INTEGRATION.md)。

## 官方兼容端点参考

- DeepSeek：`https://api.deepseek.com`，默认模型 ID `deepseek-flash`（当前显示名 DeepSeek-V4.1-Flash）。官方模型目录、首次调用指南和发布说明均列出该 ID；旧 `deepseek-v4-flash` 已退役并临时路由到新模型。[模型目录](https://api-docs.deepseek.com/api/list-models/)、[首次调用指南](https://api-docs.deepseek.com/guides/codex)、[V4.1-Flash 发布说明](https://api-docs.deepseek.com/news/news260910/)
- OpenAI：`https://api.openai.com/v1`，默认模型 `gpt-5-mini`。请按账户可用模型调整。[官方模型目录](https://developers.openai.com/api/docs/models/all)
- SiliconFlow：`https://api.siliconflow.cn/v1`，默认模型 `deepseek-ai/DeepSeek-V4-Flash`。[官方 Chat Completions 文档](https://docs.siliconflow.cn/docs/api/chat-completions-post)
- 阿里云百炼：预设北京公共兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`，默认模型 `qwen-plus`。其他地域/业务空间可能要求不同 URL 和 Key。[官方 OpenAI 兼容说明](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)

## 测试

```powershell
py -3.13 -m pip install -r requirements-dev.txt
py -3.13 -m pytest -q
py -3.13 -m compileall -q main.py filemind tests tools
py -3.13 -m pip check
```

`.github/workflows/ci.yml` 配置 Windows、Ubuntu、macOS + Python 3.13 自动测试及安装包资源检查。工作流已配置不代表本次已经在远端三平台运行；本机验证结果见 [队友改动整合记录](docs/BRANCH_INTEGRATION.md)。

AI 测试使用 mock，不调用真实密钥或网络。Qt 集成测试使用 `QT_QPA_PLATFORM=offscreen` 和临时目录。

可以用隔离工具检查界面，不读取 `.env`、环境 API Key、Windows API 凭据或真实历史记录：

```powershell
py -3.13 tools/review_ui.py --isolated --page setup --width 920 --height 660
py -3.13 tools/review_ui.py --isolated --page preview --width 1024 --height 700
py -3.13 tools/review_ui.py --isolated --page orbit --width 1280 --height 850
py -3.13 tools/review_ui.py --isolated --page conversion --width 1024 --height 700
py -3.13 tools/review_ui.py --page chat --snapshot .artifacts/ui-review/chat.png
```

工具中的文件、路径、会话是临时生成的验收数据，不代表真实模型回答。正式使用仍从 `main.py` 启动。历史改造记录见 [界面改造说明](docs/UI_REDESIGN.md)，五阶段变更见 [工作区改造验收](docs/WORKSPACE_REDESIGN.md)。

普通运行 tools/review_ui.py（没有 --isolated 或 --snapshot）现会启动正式应用，使用可持久化的设置和账户。只有显式隔离或截图模式使用临时目录，隔离模式中手动填写的密钥仅在本进程保留，退出后清理；不要把它用作日常工作区。本轮详细变更、依赖许可证和测试记录见 [第三轮整改验收](docs/ROUND3_REDESIGN.md)。

后续聊天与下拉菜单优化见 [第四轮 UI 验收](docs/ROUND4_ORBIT_UI.md)。模型连接从侧栏“模型配置”进入；各页面顶部不再重复显示模型设置按钮。通用设置位于头像菜单，`Ctrl+,` 打开通用设置。补齐的主题、图标和入口见 [第七轮整合记录](docs/ROUND7_MODEL_SETTINGS_THEMES.md)。

内容识别命名、格式扩展、QSS 卡片及最新测试结果见 [第五轮验收记录](docs/ROUND5_CONTENT_CONVERSION_QSS.md)。

## 目录结构

```text
filemind/
  ai/          服务接口、provider 预设、提示词、结构化校验、OpenAI SDK 适配
  core/        扫描、分类、整理计划安全校验、执行与撤销
  conversion/  本地格式识别、转换能力与安全输出
  models/      文件操作与聊天数据模型（保留旧导入兼容）
  storage/     操作历史、普通设置、Windows 凭据存储
  ui/          PySide6 页面、模型视图、后台任务
tests/         核心、AI、设置持久化及 UI 集成测试
main.py        应用入口
```

## 已知限制

- 只支持 OpenAI Chat Completions 兼容接口；每个模型与服务商配置仍需使用“测试连接”实测。
- 默认 AI 整理仍只发送元数据。需要内容分类/命名时，选择“按内容分类与命名 · AI”，每次确认后才读取和发送正文片段或图片缩略图；模型判断质量不能由本地保证。
- Windows 凭据管理器是推荐密钥存储；明文本地存储只能作为用户明确选择的降级方案。
- 仅处理所选目录第一层，不递归扫描。撤销基于文件大小和修改时间检查，无法识别同时恢复这两项属性的内容改写。
