# FileMind 文件整理助手

FileMind 是一个 Python + PySide6 桌面文件整理工具，可在 Windows、macOS 和 Linux 上运行（Windows 是主要验证目标）。它可用本地规则分类，也可调用配置好的 OpenAI Chat Completions 兼容服务生成分类、相对目标子目录和可选改名建议。所有建议都要经过本地安全校验并由用户确认后，才会交给本地执行器。

## 当前功能

- 只扫描用户明确选择的目录第一层普通文件，不递归，不读取文件正文。
- 本地规则支持按文件类型或修改年月分类，可离线使用；课程/项目语义预设需要在线 AI，不会把本地规则结果显示成 AI 结果。
- 主工作区先显示导入文件清单；选择分类方式、输入规则后，点击发送或按 Enter 生成建议，Shift+Enter 换行。目标树和详情表支持联动核对，再单独打开预览确认执行。
- AI 可建议分类、分类下相对目录、理由和保留扩展名的可选新文件名；稳定文件 ID 用于关联结果，不使用模型行号。
- 大文件夹按文件数量和序列化长度分批请求；失败批次会显示在对应预览行，部分 AI 结果不会伪装为完整成功。
- 预览包含原路径、目标路径、原名、新名、分类、理由、建议来源和本地校验状态；可直接双击修改分类或新文件名，或取消勾选“执行”列排除某一行，修改会立即重新校验。
- 目标冲突不再阻断整批：冲突、符号链接、AI 批次失败和你手动排除的行会在执行时逐条跳过，其余文件照常处理，执行结果分别报告成功、跳过和失败数量。
- 同一分类内出现重名目标时，计划器会自动追加 `(2)`、`(3)` 等后缀，既不覆盖已有文件，也不会因为一个重名让整份计划作废。
- AI 不能选择绝对路径、执行代码、Shell 命令或直接操作文件。核心计划器检查路径、文件名、重名、目标冲突和符号链接；执行器不覆盖文件，记录历史并支持撤销。
- 扫描、连接测试、AI 请求和文件操作在后台线程中进行。
- Orbit 是独立通用对话页面，支持本地会话、新建/切换/删除、Markdown 回答、快捷任务、停止与重试；附件需用户明确选择并在发送前确认。
- 侧栏可通过顶部按钮或 `Ctrl+B` 收起/展开，可拖动分隔线调整至 230–380px，宽度和收起状态会保存在本机。
- 独立格式转换页：图片编码与图片转单页 PDF、文本编码与 HTML/DOCX/XLSX/YAML/XML 转换、CSV/JSON 互转、PDF 文本层与页面图像、音视频重编码、DOCX/XLSX/PPTX 内容提取、EPUB 章节文字和单文件 ZIP；只显示当前文件和本机后端真正支持的目标，缺少后端时不会列出该目标。
- Orbit 附件第一版支持 PNG/JPEG/GIF/WebP 图片（仅 DeepSeek V4.1 Flash 已核验图像输入）及 UTF-8 文本/代码文件；单个附件上限 4 MB，每次最多 5 个、总量 12 MB。PDF、Office 文档和多模态模型自动探测尚未实现。

## 安装与启动

需要 Python 3.13。运行依赖见 `requirements.txt`：PySide6 Essentials、OpenAI SDK、Pillow、pypdfium2、PyYAML、python-docx、openpyxl、python-pptx、defusedxml、imageio-ffmpeg。

推荐使用项目内的独立虚拟环境，避免污染系统解释器：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

```bash
# macOS / Linux：命令等价，只是路径不同
python3.13 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python main.py
```

如果本机没有 `py` 启动器，把 `py -3.13` 换成 Python 3.13 解释器的完整路径。也可以直接安装本仓库：`pip install -e .`（元数据在 `pyproject.toml`，同时提供指向 `filemind.ui.main_window:main` 的 `filemind` 命令）。

### 跨平台支持

CI 在 Windows、Ubuntu 和 macOS 上运行同一套检查和测试；三端的差异只集中在少数系统集成点上：

| 能力 | Windows | macOS / Linux |
| --- | --- | --- |
| 界面、整理流程、格式转换、Orbit 对话 | 支持 | 支持（Linux 需要 Qt 运行所需的系统库，CI 已按官方依赖列表安装） |
| 中文字体 | 依次尝试微软雅黑、等线、宋体 | 依次尝试苹方、冬青黑体、Noto Sans CJK、文泉驿 |
| 文件类型图标 | 使用系统关联图标 | 使用内置矢量图标，不调用系统外壳 |
| 配置与数据目录 | `%APPDATA%\FileMind`、`%LOCALAPPDATA%\FileMind` | macOS 用 `~/Library/Application Support/FileMind`；Linux 遵循 XDG（`~/.config/FileMind`、`~/.local/share/FileMind`，可用 `XDG_CONFIG_HOME`/`XDG_DATA_HOME` 覆盖） |
| “记住解锁 7 天” | 支持（DPAPI 保护的随机令牌） | 不支持；解锁页会禁用该选项并说明原因，需每次输入密码 |
| API Key 存储 | 默认 Windows 凭据管理器 | 没有系统凭据存储可用；使用环境变量或显式勾选本机明文保存（权限 0600） |
| 移动文件 | `os.rename`（同一目录树内） | 先 `os.link` 再删除源文件，失败会回滚，同样不覆盖 |

## 本机密码与锁屏

首次从 `main.py` 启动时设置本机密码（至少 8 个字符），并保存一次性显示的恢复码。下次启动使用密码解锁后才会加载工作区。左下角本机用户菜单、设置页的“本机工作空间”可手动锁定或修改密码；快捷键是 `Ctrl+L`。运行中的文件/API 任务需先完成或停止，再锁定。

密码不以明文保存：应用使用 16 字节随机盐、600,000 次 PBKDF2-HMAC-SHA256 和常量时间比较。验证值位于 `%LOCALAPPDATA%/FileMind/lock/auth.json`，写入前限制文件为当前用户访问，采用原子替换。连续五次失败会等待 30 秒。

“记住解锁 7 天”保存 Windows DPAPI 保护的随机令牌，不保存密码，也不使用 API Key 的凭据存储；令牌到期、手动锁定和修改密码都会使其失效。忘记密码可在解锁页输入恢复码重设，新恢复码会替代旧码；文件、聊天和模型设置保留。密码和恢复码都遗失时，没有应用内绕过入口，请勿删除其他配置或数据。锁屏是应用级访问提示，不等同于 Windows 账户安全、文件加密或防止本机管理员修改程序。

左下角用户菜单可更换本机头像或“锁定 / 登出”。头像仅接受用户主动选择的 PNG/JPEG/WebP/BMP，最大 8 MB、1600 万像素，保存为去除原始元数据的 128×128 PNG，不上传、不写入聊天历史。头像和侧栏偏好位于 `%LOCALAPPDATA%/FileMind/` 的 `avatar.png`、`workspace.json`，不涉及模型密钥配置。

## 本地格式转换

在侧栏打开“格式转换”，选择或拖入一个文件，等待识别后选择目标，点击“开始转换并保存…”，指定一个尚不存在的输出文件。源文件保留，已有输出不会覆盖；可以取消尚未发布的任务。编码期间取消会在安全停止点生效，结果发布完成后会如实显示成功。每次只处理一个文件，整个过程不调用 AI、不联网。

| 输入 | 真实实现 | 限制 |
| --- | --- | --- |
| PNG/JPEG/WebP/BMP/GIF/TIFF/AVIF/ICO/TGA/PCX/PPM 等单帧图片 | Pillow 实际可写的编码格式（本机为 PNG/JPEG/WebP/BMP/TIFF/GIF/AVIF）、图片 → 单页 PDF | 动图和多页输入拒绝转换；JPEG、AVIF 有损且透明区域填白；不承诺保留 EXIF 与色彩配置；无 OCR |
| TXT/Markdown/代码/日志/CSV/JSON/HTML/XML/YAML | UTF-8 或带 BOM 的 UTF-16 文本输出 | 输入仅接受 UTF-8 或带 BOM 的 UTF-16，不猜测其他编码 |
| CSV | JSON 字符串记录数组、XLSX 工作表 | 表头不能重复或为空，列数必须一致；XLSX 单元格按文本写入，不写成公式 |
| JSON | 格式化 JSON、扁平对象数组转 CSV、JSON ↔ YAML | 嵌套结构拒绝转 CSV，避免静默丢失信息 |
| HTML | 提取可见文本 | 忽略脚本和样式，不加载外部链接 |
| DOCX / PPTX | 段落、表格、文本框文字 → TXT 或静态 HTML | 不保留版面、图片和公式；PPTX 不导出备注与动画 |
| XLSX | 全部工作表值 → JSON 或每表一个 CSV 的 ZIP | 只读缓存值，不计算公式、不连接外部数据；每表限 50000 行 / 200 列 |
| PDF（未加密，1–100 页） | 文本层 → TXT、逐页渲染 → PNG/JPEG 页面 ZIP | 本地 PDFium；扫描版无文本时明确提示，不含 OCR，不保留交互表单 |
| MP3/WAV/FLAC/Ogg/AAC/M4A 等音频 | 重新编码为 MP3/WAV/FLAC/Ogg | 依赖 FFmpeg（默认由 `imageio-ffmpeg` 提供，也可用系统安装的版本）；重新编码可能有损，只处理首个音轨 |
| MP4/MOV/MKV/WebM/AVI/WMV 等视频 | 重新编码为 MP4/WebM/MKV | 同上；不保留字幕与封面，单文件限 64 MB / 5 分钟处理时间 |
| EPUB | 按阅读顺序提取章节文字 | 不处理 DRM，不读取外链 |
| DOC/DOCX/XLS/XLSX/PPT/PPTX/ODT/ODS/ODP/RTF | 经本机 LibreOffice 转 PDF 或对应 Office/ODF 格式（实验性） | 需自行安装 LibreOffice，未安装时该组目标不出现在界面；排版、字体和公式结果可能变化 |
| 任意普通文件 | 单文件 ZIP 打包 | 不递归文件夹、不解压，源文件保持不变 |

单个输入最大 64 MB，文本转换最大 8 MB，图片最大 3200 万像素。转换先写入输出目录中的临时文件，再检查源文件状态并以不覆盖方式发布。可用目标按本机真实安装的后端动态显示：缺少对应库或外部程序时界面不会列出该格式，也不提供占位式的假转换。

## 树状整理预览

独立预览展示目标根目录、蓝色文件夹、嵌套子目录和目标文件；图标、箭头与数量来自当前本地校验的计划，不会额外遍历文件夹。支持展开/折叠、名称/目标路径/理由搜索，以及选中目录或文件联动详情。目录按路径层级筛选，文件按精确路径筛选。完整名称与路径可以在提示和下方详情中查看、选取复制。

树中“待执行”表示尚未操作，表格“通过”表示本地校验通过。异常或重名冲突会在节点和摘要中显示，并在执行时跳过；只有全部行都会被跳过时才会禁用执行。表格可编辑：双击“建议新文件名”或“分类”单元格修改建议，取消勾选“执行”列排除某一行，无法保留扩展名或不合法的名称会被拒绝并说明原因。之后仍需经过主窗口二次确认，执行器会再次校验，不覆盖文件，并分别报告成功、跳过和失败数量。

## AI 服务配置

首次使用时默认选择 DeepSeek，Base URL 为 `https://api.deepseek.com`，模型 ID 为 `deepseek-flash`（官方显示名 DeepSeek-V4.1-Flash）。API Key 不预置；请在“设置”中填写自己的密钥。首次配置不会覆盖用户已保存的 provider profile。也可以选择 OpenAI、硅基流动、阿里云百炼或自定义兼容接口。可以修改 Base URL、模型名称、请求超时和 API Key。预设只提供建议值；模型是否对账户开放取决于服务商、区域和账户权限。兼容性以 Chat Completions 为目标，不支持只提供 Responses API 或专有请求格式的服务。

API Key 默认保存在 Windows Credential Manager；普通配置写入当前用户的 FileMind 配置目录（Windows 为 `%APPDATA%/FileMind`，macOS 为 `~/Library/Application Support/FileMind`，Linux 为 `~/.config/FileMind`）。切换服务商后需保存配置。环境变量可按 provider 设置：`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`SILICONFLOW_API_KEY`、`DASHSCOPE_API_KEY` 或 `FILEMIND_API_KEY`。密钥读取优先级为：系统凭据存储 → 用户明确选择的本地密钥文件 → provider 环境变量 → 旧版项目 `.env` 中的 `DEEPSEEK_API_KEY`（仅 DeepSeek）。设置页会显示密钥来源；`.env.example` 仅为空占位，不会自动加载。

如果没有可用系统凭据存储（macOS 与 Linux 属于这种情况），用户可显式勾选“本机配置文件明文保存”。该文件位于 FileMind 配置目录，Windows 下限制为当前用户，其他系统设为 0600；明文保存存在风险，不推荐开启。密钥不会写入普通设置、操作历史、源码或错误提示。

第一次生成在线 AI 预览前会询问授权。发送字段包括文件名、扩展名、大小、修改时间和用户规则；不会发送文件正文、整个文件夹或绝对路径。请求需要联网，在线 AI 不是离线功能。每次连接测试都会真实请求所选服务商，可能产生少量 token 费用；没有真实服务配置时不要把 mock 测试结果当作连接成功。

Orbit 首次发送消息前会单独询问授权。发送范围是你输入的消息与当前会话最近上下文，服务商由“设置”页当前已保存的配置决定。添加附件时，每次发送前还会列出文件名并再次确认；被选中文件的内容会发送给当前服务商。聊天记录保留附件文件名，不保留本地路径或附件正文；应用重启后如需重试含附件消息，需要重新选择附件。Orbit 不会自动访问本机文件或文件整理记录。会话保存在 `%APPDATA%/FileMind/chat_history.json`，不保存 API Key。模型切换并保存后，之后的新请求直接使用新配置，无需重启。

## 官方兼容端点参考

- DeepSeek：`https://api.deepseek.com`，默认模型 ID `deepseek-flash`（当前显示名 DeepSeek-V4.1-Flash）。官方模型目录、首次调用指南和发布说明均列出该 ID；旧 `deepseek-v4-flash` 已退役并临时路由到新模型。[模型目录](https://api-docs.deepseek.com/api/list-models/)、[首次调用指南](https://api-docs.deepseek.com/guides/codex)、[V4.1-Flash 发布说明](https://api-docs.deepseek.com/news/news260910/)
- OpenAI：`https://api.openai.com/v1`，默认模型 `gpt-5-mini`。请按账户可用模型调整。[官方模型目录](https://developers.openai.com/api/docs/models/all)
- SiliconFlow：`https://api.siliconflow.cn/v1`，默认模型 `deepseek-ai/DeepSeek-V4-Flash`。[官方 Chat Completions 文档](https://docs.siliconflow.cn/docs/api/chat-completions-post)
- 阿里云百炼：预设北京公共兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`，默认模型 `qwen-plus`。其他地域/业务空间可能要求不同 URL 和 Key。[官方 OpenAI 兼容说明](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)

## 测试

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q main.py filemind tests tools
```

当前完整套件为 146 passed、24 subtests passed（约 30 秒；最近一次验收环境为 Python 3.13.15 + pytest 9.1.1）。同样这三条命令也会在 `.github/workflows/ci.yml` 中按 Windows、Ubuntu 和 macOS 三个平台 + Python 3.13 自动运行。

AI 测试使用 mock，不调用真实密钥或网络。Qt 集成测试使用 `QT_QPA_PLATFORM=offscreen` 和临时目录。

可以用隔离工具检查界面，不读取 `.env`、环境 API Key、Windows API 凭据或真实历史记录：

```powershell
.\.venv\Scripts\python.exe tools/review_ui.py --page setup --width 920 --height 660
.\.venv\Scripts\python.exe tools/review_ui.py --page preview --width 1024 --height 700
.\.venv\Scripts\python.exe tools/review_ui.py --page orbit --width 1280 --height 850
.\.venv\Scripts\python.exe tools/review_ui.py --page conversion --width 1024 --height 700
.\.venv\Scripts\python.exe tools/review_ui.py --page chat --snapshot .artifacts/ui-review/chat.png
```

工具中的文件、路径、会话是临时生成的验收数据，不代表真实模型回答。正式使用仍从 `main.py` 启动。[界面改造说明](docs/UI_REDESIGN.md) 与 [工作区改造验收](docs/WORKSPACE_REDESIGN.md) 是 2026-10-15 的历史验收记录，其中的能力边界早于后续转换层扩展；当前的工程化收尾、运行与校验方式见 [进度报告](docs/PROGRESS_REPORT.md)，能力边界以本文件与代码为准。本项目还提供 `.agents/skills/filemind-desktop-ui/SKILL.md`，便于后续开发沿用当前 Qt 布局与安全约定。

## 目录结构

```text
filemind/
  ai/          服务接口、provider 预设、提示词、结构化校验、OpenAI SDK 适配
  core/        扫描、分类、组织预设、整理计划安全校验、执行与撤销
  conversion/  本地格式识别、转换能力与安全输出（图片、文本、PDF、Office、音视频）
  storage/     操作历史、普通设置、跨平台目录、Windows 凭据存储、本机锁屏、工作区偏好
  ui/          PySide6 页面、模型视图、后台任务
tests/         核心、AI、设置持久化、锁屏及 UI 集成测试
tools/         review_ui.py 隔离界面检查与截图
docs/          历史界面与工作区改造验收记录
main.py        应用入口
pyproject.toml 包元数据、入口点与开发依赖
```

## 已知限制

- 只支持 OpenAI Chat Completions 兼容接口；每个模型与服务商配置仍需使用“测试连接”实测。
- 第一版只将元数据作为 AI 输入，无法理解文件正文；转换页已有的文本抽取能力尚未接入 AI 分类。模型给出的语义分类质量无法由本地保证。
- 预览只能修改分类、分类下的相对子目录和新文件名，不能把某一行移动到任意位置；重名目标由本地自动追加序号，用户不能自行指定冲突处理方式。
- Windows 凭据管理器是 v1 实现的唯一系统凭据存储；macOS 与 Linux 需要环境变量或用户明确选择的明文文件，未接入 Keychain/SecretService。
- “记住解锁 7 天”依赖 Windows DPAPI，其他系统不提供该选项；锁屏功能本身三平台都可用。
- 仅处理所选目录第一层，不递归扫描。撤销基于文件大小和修改时间检查，无法识别同时恢复这两项属性的内容改写。
- Office 排版转换依赖本机 LibreOffice，音视频转换依赖 FFmpeg，两者都不随项目分发，也未在 CI 中验证。
- 操作历史写在被整理目录的 `.filemind/history/` 内，目录被移动或改名后历史不会跟随。
