# FileMind 第三轮整改与验收

日期：2026-10-16。以当前源码和实际运行结果为准；本轮开始的基线是 134 项测试、24 项子测试通过（44.11 秒）。初查时 Git 不可用，收尾时 `git status --short` 已可用并显示工作区修改；本轮未执行 Git 初始化、重置或提交，也未回退期间出现的模型目录调整。

## 已完成的行为

### 配置保存

截图报错来自上一轮临时 UI 验收工具的 ReviewSettings.save 固定抛错，而非正式 SettingsStore。现已移除此拒绝逻辑：普通启动 review_ui 工具也进入正式应用，使用持久化设置和既有 Windows 凭据管理器；只有显式 --isolated 或截图模式使用临时数据。无需修改 main.py 或源码才能保存。

临时验收模式也允许编辑和保存，密钥仅保留在注入的隔离会话中，并显示准确保存范围；它不加载真实 .env、环境 API Key、Windows 凭据或用户聊天。正式应用的重启恢复通过临时目录、注入 SecretStore 测试，不声称实际访问过用户凭据。

另修复设置页初始化硬编码 DeepSeek 的问题：保存过的 active_provider 优先恢复，下拉框、模型与对应密钥一起显示。保存不等于连接成功；空密钥显示未配置，加载时重新隐藏密钥，异常信息脱敏。右上角“模型设置”和 Ctrl+, 提供直接入口。

### 整理工作区

- 规则区与文件工作区放入垂直 QSplitter，可拖动且记住高度；恢复使用真实可用高度，保留底栏和最低文件区空间。
- 类型、修改年月为本地分类；课程、项目、用途/主题、自定义为 AI 预设。自然语言文本可修改，替换已编辑内容仍询问，避免误丢规则。
- 原有发送按钮、Enter/Shift+Enter、输入法候选保护、后台任务、失败和取消状态保留；Tab 可移到发送按钮。
- 扫描前清单与校验后目标树保留。文件图标按扩展名查询 Windows 关联，不读取正文、不运行缩略图处理器；缓存最多 128 种扩展名，失败使用统一类型图标。
- 空态区分未选择、已选择未读取和真正空目录。按钮分别选择目录、读取文件或选择其他目录；四类轻量彩色卡提供下一步说明，导入后收敛成表格。
- 紧凑统计、进度、上次任务摘要和历史入口保留。独立预览、确认、执行器复检、不覆盖、部分失败和撤销没有取消。

### 账户、侧栏与 Orbit

复用已有的头像选择、PBKDF2 本地锁、恢复码、改密、锁定/登出；没有另建账户系统或读取密码。侧栏仍可隐藏、拖动和恢复；Orbit 继续独立处理会话、附件确认、模型切换和请求状态。只调整公共入口和布局，不把文件整理数据自动送入聊天。

### 真实本地转换

服务分为统一安全发布器和格式适配器。适配器只能写入调用者拥有的暂存文件；发布器重新验证源状态、取消、输出路径与重名，再以不覆盖操作发布。文件仅在本地处理。

| 类别 | 实测支持 | 限制 |
| --- | --- | --- |
| 图片 | PNG/JPEG/WebP/TIFF/BMP/GIF/AVIF 当前编码器逐一写出并读回；图片转单页 PDF | 仅单帧，拒绝多页/动图；RAW/HEIC 未接入 |
| PDF | 文本层提取、逐页 PNG ZIP | JPEG ZIP 同一适配器；最多 100 页；无文本层会提示，不提供 OCR 或可编辑 Word |
| 文本 | HTML、XML、JSON/YAML、CSV/XLSX、EPUB 章节文字和文本编码 | UTF-8/UTF-16；不执行脚本，不加载外链；禁用 XML 实体、YAML 对象标签/别名 |
| DOCX | 段落/表格文字及静态 HTML | 非版面复刻，不保留图像 |
| XLSX | 全部工作表 JSON/CSV ZIP | 不执行公式，只读已有缓存值；限制行列和总单元格 |
| PPTX | 按页文字提取 | 无动画、讲者备注和版面导出 |
| 音频 | 实际 WAV→MP3/FLAC 并重新解码 | 其他目标按本机编码器探测；可能有损，保留首个音轨 |
| 视频 | 实际短 MP4→VP9 WebM 并重新解码 | 固定本地编码参数；无字幕/封面/多轨完整保留承诺 |
| Office 排版 | LibreOffice 适配器已实现，缺后端时不提供目标 | 当前机器未安装 LibreOffice，未做真实排版转换验证，标记实验性 |
| ZIP | 单个普通文件打包 | 不递归、不解压，源文件保留 |

彩色能力卡区分已实现、内容提取、值导出、后端已安装、实验性和不可用。编码期间进度不确定时使用等待状态，没有伪造百分比。FFmpeg 使用固定参数、显式本地解复用器和文件协议，不调用 Shell，取消只终止本次子进程。

PDFium 官方文档明确它不能跨线程并发调用，PDF 适配器使用全局互斥并显式关闭页面、位图和文档。[官方 Python API](https://pypdfium2.readthedocs.io/en/stable/python_api.html)

测试发现并修复了无效 XML 的 ParseError、损坏 EPUB 的 KeyError 直接流入界面的情况；现返回明确且不含文件正文的转换错误。

## 模型目录兼容

工作过程中发现模型文件已被移入 filemind/models/。保留这部分结构，通过 models/__init__.py 导出原公共类型，并提供旧 filemind.chat_models 的兼容重导出，避免现有页面、服务和测试导入失败。没有把已移动的模块再搬回。

## 依赖与许可证

继续使用 Python 3.13、PySide6 Essentials 6.12.0 和 OpenAI SDK 2.54.0。构建系统没有迁移；requirements.txt 新增以下本地转换依赖：

| 名称 | 本机/锁定版本 | 用途 | 许可证 |
| --- | --- | --- | --- |
| Pillow | 12.0.0 | 图片编码及 PDF 页面图像保存 | MIT-CMU |
| pypdfium2 | 5.14.0 | PDF 文本/页面渲染 | BSD-3-Clause / Apache-2.0，附 PDFium 第三方通知 |
| PyYAML | 6.0.3 | 安全 JSON/YAML 转换 | MIT |
| python-docx | 1.2.0 | DOCX 提取和文本建文档 | MIT |
| openpyxl | 3.1.5 | XLSX 数据和文本单元格 | MIT |
| python-pptx | 1.0.2 | PPTX 文本提取 | MIT |
| defusedxml | 0.7.1 | XML/EPUB 实体防护 | PSFL |
| imageio-ffmpeg | 0.6.0 | 提供本机 FFmpeg 可执行文件 | Python 包 BSD-2-Clause |

本机捆绑 FFmpeg 为 7.1，构建启用 GPL 与 version3；它的许可证不同于 Python 包，分发二进制时需要履行对应 GPL 和第三方通知义务。本轮没有打包分发。新增传递安装项 XlsxWriter 3.2.9 为 BSD-2-Clause；lxml 6.0.2（BSD-3-Clause）等既有环境项由声明依赖解析，不复制进源码。许可证信息取自实际安装包元数据与官方仓库。

## GitHub 与技能

- 从 [Qt 官方 agent-skills](https://github.com/TheQtCompanyRnD/agent-skills) 安装 qt-ui-design 1.1，用于布局、反馈、键盘导航和内容优先级；许可证为 LicenseRef-Qt-Commercial OR BSD-3-Clause。
- 从 [morluto/rea](https://github.com/morluto/rea) 安装 reverse-engineer-anything 技能（元数据版本 42），许可证 MIT；技能及源仓库 LICENSE 已保存在本机技能目录。
- REA 技能不等于 REA MCP 已连接，也不包含 Ghidra/IDA 等分析引擎。当前有完整源码，不为普通源码分析启动逆向工具；后续在有逆向目标时按用户授权配置，商业引擎仍需合法授权。
- 使用项目既有 filemind-desktop-ui 与 Product Design 的参考图/可用性检查方法，没有把桌面应用换成网页原型，也没有复制其他项目控件代码。
- GitHub 连接器核实了 REA、Qt 技能、PDFium 和 FFmpeg Python 封装来源。Exa 本轮调用返回 INVALID_ARGUMENT，未把该调用当成有效搜索证据。

未提供 Figma 文件或节点链接，因此本轮直接依据用户截图和已有 Qt 设计体系实现，没有声称从 Figma 读取设计。

## 修改文件

| 文件/目录 | 变化 |
| --- | --- |
| filemind/ui/pages/settings_page.py | 保存反馈、恢复服务商、密钥显示/脱敏 |
| tools/review_ui.py | 正式启动与显式隔离分流，移除保存拒绝 |
| filemind/storage/workspace.py | 保存整理区高度 |
| filemind/ui/main_window.py | 高度恢复、直接模型入口、布局保存 |
| filemind/core/organization_presets.py | 增加用途/主题 AI 预设 |
| filemind/ui/pages/organize_page.py | 上下分隔、空态、焦点与信号 |
| filemind/ui/widgets/organizer_empty.py、organization_workspace.py | 三态导入引导、表格收敛 |
| filemind/ui/styles/file_icons.py、widgets/imported_files.py、widgets/plan_tree.py | 缓存 Windows 关联图标及备用图标 |
| filemind/ui/styles/theme.py、widgets/format_cards.py | 分隔条和彩色响应式能力卡 |
| filemind/ui/pages/conversion_page.py | 使用真实能力目录 |
| filemind/conversion/base.py、adapters.py、capabilities.py | 公共错误、注册路由与能力模型 |
| filemind/conversion/images.py、pdf.py、documents.py、text.py、media.py、office.py | 格式适配器 |
| filemind/conversion/service.py | 保留统一安全输出，接入适配器、删除废弃分支 |
| filemind/__init__.py、models/__init__.py、chat_models.py | 兼容模型迁移 |
| tests/test_configuration_flow.py、test_extended_conversion.py、test_workspace_layout.py、test_workspace_preferences.py | 新增和加强验证 |
| requirements.txt、README.md、本文件、design-qa.md | 安装、限制、来源和验收 |

## 实际验证

基线完整测试：134 passed、24 subtests passed。最终运行 `py -3.13 -m pytest -q`：175 passed、24 subtests passed，128.56 秒，退出码 0。其中新增配置测试 10 项、扩展转换测试 25 项、布局测试 5 项及整理区域高度跨窗口重启恢复测试 1 项；没有删除或降低旧断言。

编译：`py -3.13 -m compileall -q main.py filemind tests tools`，通过。依赖：`py -3.13 -m pip check`，No broken requirements found。新模型路径的旧/新导入相同对象，主窗口导入通过。正式 `run_application()` 启动检查使用临时锁屏存储，实际显示首次设置界面后取消，退出码 0；确认取消后没有创建主窗口、加载用户设置或凭据。

实际 Qt 启动截图检查：1024×700 和 1280×850 的空态、清单/目录树；1024×700 转换能力页、设置和 Orbit；1280×850 转换页。QTest 检查真实分隔条拖动、Enter/Shift+Enter/Tab、底栏可见、卡片重排、导入后隐藏空态。所有文件和模型回复均为临时生成数据；转换使用真实本机后端，模型 API 使用 mock。

没有读取用户 .env、Windows 凭据或真实密钥，没有对用户真实目录自动执行整理；没有用 mock 结果声称真实模型连通。真实 API 连接仍需用户在设置里自行测试。LibreOffice、OCR、RAW/HEIC、WPS 专有格式和所有复杂排版场景不在本轮已验证范围。
