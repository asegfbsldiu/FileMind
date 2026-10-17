# 第五轮：内容分类、真实格式转换与 QSS 美化

日期：2026-10-16。保留 Python 3.13、PySide6 Qt Widgets、OpenAI SDK；没有迁移界面框架，也没有改写执行器或凭据存储。工作区原有 Claude 和队友改动继续保留。

## 1. 图一问题与内容分类

截图选择的是“按修改年月 · 本地”。这个预设只根据修改时间产生年月文件夹，既不会理解图片，也不会自动改名；“应用 AI 改名”此前仍在本地模式显示，容易造成误解。本轮让该选项只在 AI 模式显示，并明确提示本地分类的能力边界。

新增“按内容分类与命名 · AI”，自动启用内容识别和改名建议。用户也可在其他 AI 预设中手动勾选内容理解。默认仍为元数据模式；每次读取正文前必须单独确认所选服务商、模型和数据范围，取消时不读正文、不发请求、不操作文件。

支持范围：

- 文本、代码：UTF-8 或带 BOM 的 UTF-16，开头最多 1800 字。
- PDF：前三页的文本层，合计最多 1800 字；无 OCR。
- DOCX、XLSX、PPTX：受限 OOXML 文本片段，不运行宏、公式或外部链接。
- 单帧图片：去除 EXIF、等比缩至最长 1024 像素后发送 JPEG。图像协议本轮只按 DeepSeek 官方文档启用 `deepseek-flash`；其他模型明确提示限制。
- 每次最多 128 个文件，单文件不超过 8 MB，图片请求数据总量最多 12 MB；每个模型批次最多 4 张图片，原有文本批次上限继续生效。

`.env`、疑似密码、凭据、私钥等名称在打开文件前排除；片段中常见凭据模式进行遮蔽。此机制不是完整的数据脱敏器，图片中的个人信息仍可能发送，确认框已说明。无法解析、超限和不支持的文件均按稳定 ID 返回失败，显示校验警告并跳过执行。

所有内容只在当前任务内存中处理；操作历史不保存正文或图片。模型返回的分类和名称继续走原有严格 JSON 校验、路径校验、冲突检查、预览编辑、明确确认及执行/撤销。

## 2. 转换页与 QSS

新增集中管理的 `filemind/ui/styles/conversion.qss`，由现有主题统一加载：

- 浅米色拖入区、薄荷绿/浅蓝/淡黄/淡紫能力卡片。
- 统一圆角、标题字号和字重，输入/输出列表使用逗号分隔。
- 卡片根据内容区宽度显示 1–5 列；实际主窗口 1024×700 为两列，1280×850 为三列。
- 顶部步骤条有独立最小高度，不再被能力卡片挤压；窄内容区将左右工作区改成上下布局。
- 后台查询实际 FFmpeg 编码器后更新音视频列表；探测失败则隐藏相关卡片，文件转换任务与能力探测状态分开。
- 选择文件旁的 × 和不覆盖保存逻辑继续保留；关闭应用会等待有界的后台探测结束，探测不阻止本机锁屏。

真实新增转换：

| 类别 | 新增能力 | 校验方式 |
| --- | --- | --- |
| 图片 | ICO、TGA、PCX、PPM | Pillow 重新打开并验证真实格式；ICO 等比居中留白 |
| 电子书 | 文本 → 含目录 EPUB 3 | 检查 ZIP、mimetype、OPF/XHTML，并重新提取章节文字 |
| PDF | 文本层 → DOCX、静态 HTML | 真实生成文档再读取文字；不承诺版面还原 |
| 音频 | AAC、M4A、Opus、WMA | FFmpeg 将生成结果完整解码至空输出验证 |
| 视频 | MOV；增加 FLV、MPG/MPEG、M2TS 输入路由 | 生成短视频，转换 MOV 后重新解码验证；新增输入容器仍以本机解码器识别为准 |
| 字体 | TTF/OTF → WOFF/WOFF2；压缩容器 → 原始 TTF 或 OTF | 生成测试字体，压缩往返后检查字符映射和字形表 |

字体只改变容器，不做 TrueType/CFF 轮廓互转。解析字体前限制声明大小、表数量和实际 Brotli/zlib 解压量。转换继续采用临时文件、安全检查和不覆盖发布，源文件不修改。

未增加 RAW、HEIC、OCR、全格式 Office 无损互转承诺。没有安装 LibreOffice 时不显示其排版转换卡片；PDF 转 DOCX/HTML 是文本重建。

## 3. 修改文件

| 文件 | 本轮变更 |
| --- | --- |
| `filemind/ai/content.py`（新增） | 经授权的内容快照、敏感名称排除、图像缩略、大小限制与失败关联 |
| `filemind/ai/content_readers.py`（新增） | 内存中 PDF/OOXML 片段读取 |
| `filemind/ai/schemas.py` | 可选片段、图片和内容说明字段 |
| `filemind/ai/prompts.py` | 独立内容说明和稳定 ID 图片消息组装 |
| `filemind/ai/openai_compatible.py` | 多模态内容消息、图片批次限制 |
| `filemind/core/organization_presets.py` | 内容分类命名预设 |
| `filemind/ui/main_window.py` | 每次内容授权、后台处理、原有安全计划接入及关闭任务等待 |
| `filemind/ui/pages/organize_page.py` | 内容选项、真实隐私提示、本地模式明确不改名 |
| `filemind/conversion/fonts.py`（新增） | 真实字体容器转换 |
| `filemind/conversion/font_limits.py`（新增） | 字体压缩流限额校验 |
| `filemind/conversion/epub.py`（新增） | 本地 EPUB 3 创建 |
| `filemind/conversion/images.py` | 四种图片输出和 ICO 等比留白 |
| `filemind/conversion/media.py` | 新增编码/容器、实际编码器能力查询 |
| `filemind/conversion/pdf.py` | PDF 文本重建 DOCX/HTML |
| `filemind/conversion/text.py` | EPUB 目标与路由 |
| `filemind/conversion/adapters.py` | 字体适配路由 |
| `filemind/conversion/capabilities.py` | 逗号分隔的真实能力列表 |
| `filemind/ui/widgets/format_cards.py` | 响应式卡片、后台探测状态 |
| `filemind/ui/pages/conversion_page.py` | 工作区响应式布局、步骤条及任务生命周期 |
| `filemind/ui/styles/conversion.qss`（新增） | 转换页和内容选项样式 |
| `filemind/ui/styles/theme.py` | 加载新 QSS，复用现有主题色变量 |
| `tools/review_ui.py` | 内容模式隔离验收状态，截图关闭等待后台探测 |
| `requirements.txt` | 两个字体后端依赖 |
| `tests/test_content_organization.py`（新增） | 元数据默认、授权取消、正文/图片、排除、分批、计划与预览关联 |
| `tests/test_conversion_round5.py`（新增） | 新格式真实输出、解压限额、响应式 QSS |
| `README.md`、本文 | 使用方法、能力和验收记录 |

## 4. 依赖、来源与许可

| 新增声明依赖 | 版本 | 用途 | 许可证 |
| --- | --- | --- | --- |
| fonttools | 4.67.0 | 字体解析和容器转换；本机原安装 4.61.0 已升级 | MIT |
| Brotli | 1.2.0 | WOFF2 编解码和有界解压预检 | MIT |

没有新增前端框架或修改构建配置。`pyproject.toml` 原有动态依赖和 `styles/*.qss` 打包规则已能覆盖本轮文件，wheel 资源和依赖元数据已检查。

调研的是 [FlyingMouse Format](https://github.com/LaoFeng-mouse/flyingmouse-format)，其 [许可证](https://github.com/LaoFeng-mouse/flyingmouse-format/blob/main/LICENSE) 有非商用及禁止换皮再发布的限制。本轮参考通用的卡片组织与流程展示，自行编写 Qt 布局/QSS/适配器，未复制其代码、图标、角色图片或样式文件。

其他依据：[DeepSeek 图片接口](https://api-docs.deepseek.com/guides/vision/)、[fontTools 文档](https://fonttools.readthedocs.io/en/latest/ttLib/ttFont.html)、[fonttools PyPI](https://pypi.org/project/fonttools/)、[Brotli PyPI](https://pypi.org/project/brotli/)。本轮使用 `qt-ui-design` 技能；没有创建 Figma 文件或引入新的 skill 代码。

## 5. 验证

修改前实际基线：`py -3.13 -m pytest -q`，212 项及 24 个子测试通过，耗时 459.20 秒。

本轮新增功能测试与整理工作区回归：44 项通过；锁屏控制回归：4 项通过。补充凭据命名排除后的内容模块测试：22 项通过。

最终全量命令：`py -3.13 -m pytest -q --tb=short`，**254 项及 24 个子测试全部通过，耗时 461.46 秒**。包含现有文件安全、预览编辑、冲突跳过、执行/历史/撤销、Orbit、配置、锁屏和布局回归；没有删除或跳过现有测试。

其他已完成检查：

- `py -3.13 -m compileall -q main.py filemind tests tools`。
- `py -3.13 -m pip check`：No broken requirements found。
- 入口和新增模块导入成功。
- `py -3.13 -m pip wheel . --no-deps --no-build-isolation --wheel-dir .artifacts/round5/wheels`：成功；检查了 QSS、新模块、依赖元数据。
- 将最终 wheel 安装到独立临时目录，使用 `python -I` 从仓库外导入新增模块并加载完整 QSS，成功；未替换正式用户配置。
- `git -c core.safecrlf=false diff --check`：通过。
- 隔离 Qt 实际启动：整理树、内容分类入口、转换空状态、格式卡片滚动底部；1024×700、1280×850 Qt 逻辑窗口尺寸，Windows 当前缩放约 150%。自动化另检查 600×700 独立转换页。
- 隔离界面流程检查：内容授权后，mock 模型收到真实提取的文本片段和图片消息，分类/新名称进入目录树与独立预览；拒绝执行保持源文件不变。随后通过转换页完成真实 PNG → ICO、重新解码、清除选择，源文件和结果均保留。

隔离截图位于 `.artifacts/round5/`，不进入 Git。`tools/review_ui.py --isolated --page content` 可自行查看内容模式；生成的验收文件不是用户文件，也不代表真实模型结果。

没有读取用户 `.env`、API Key 或 Windows API 凭据，没有自动移动用户文件。AI 路径使用 mock 请求验证；未进行真实服务调用，真实模型的命名/分类质量仍待用户用自己的配置和愿意发送的文件验证。

## 6. 启动

```powershell
py -3.13 -m pip install -r requirements.txt
py -3.13 main.py
```

本机已有依赖已更新，不要求新建虚拟环境。正式入口继续使用用户原有设置，内容识别需要先在设置页保存可用 AI 配置。
