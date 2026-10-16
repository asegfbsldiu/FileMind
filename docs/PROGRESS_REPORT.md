# FileMind 工程化收尾与整理预览改造报告

日期：2026-10-16。仓库：[asegfbsldiu/FileMind](https://github.com/asegfbsldiu/FileMind)（代码来源：[Frank2918/FileMind](https://github.com/Frank2918/FileMind)）。

## 一、当前状态速览

| 项目 | 状态 |
| --- | --- |
| 分支 | `main`，最新提交 `e182529`，与 `origin/main` 同步 |
| 持续集成 | 三平台矩阵（Windows / Ubuntu / macOS + Python 3.13），每次推送自动运行 |
| 测试 | 140 个测试函数；`pytest` 报 **146 passed / 24 subtests passed**（约 30 秒） |
| 静态检查 | `compileall`、`pip check`、`pyflakes` 均无告警 |
| 本地环境 | Python 3.13.15（`D:\python`）+ 项目虚拟环境 `D:\filemind\.venv`；已适配 Windows / macOS / Linux |

## 二、本次做了什么

### 1. 仓库初始化与关联

- 在 `D:\filemind` 执行 `git init`，远端 `origin` 指向你的仓库，另加 `source` 指向 `Frank2918/FileMind` 便于后续同步上游。
- 拉取上游代码（107 个文件），合并你仓库原有的 `Initial commit`，推送为快进更新，本地分支命名为 `main` 与远端默认分支一致。

### 2. 本地运行环境

- 用 winget 安装 Python 3.13.15（安装器沿用注册表记录，落在 `D:\python`），并创建项目虚拟环境 `.venv`（约 389 MB，已被 `.gitignore` 忽略）。
- 依赖见 `requirements.txt`：PySide6-Essentials、OpenAI SDK、Pillow、pypdfium2、PyYAML、python-docx、openpyxl、python-pptx、defusedxml、imageio-ffmpeg；开发依赖 `requirements-dev.txt` 追加 pytest。
- 注意：本机没有 `py` 启动器，`python` 仍是 WindowsApps 的占位符，因此命令请使用 `.venv\Scripts\python.exe` 的完整路径。

### 3. 工程化收尾（提交 `5987bc7`、`cc0e055`、`57b1f95`、`946f8f6`）

- 新增 `pyproject.toml`：包元数据、GUI 入口点 `filemind = filemind.ui.main_window:main`；运行依赖用 `dynamic` 从 `requirements.txt` 读取，避免两处清单各自漂移。
- 新增 `LICENSE`（MIT）。
- 新增 `.github/workflows/ci.yml`：在 `windows-latest` + Python 3.13 上依次执行依赖安装、`pip check`、`compileall`、`pytest`、打包元数据校验；强制 `PYTHONUTF8`，失败时把 pytest 输出写入 job 摘要并输出可匿名读取的 error annotation。
- README 与真实实现对齐：安装改为虚拟环境流程并补全依赖清单；格式转换表补齐 PDF、音视频、Office 内容提取、EPUB、YAML/XML/XLSX/DOCX/HTML 等已落地能力；删掉代码中并不存在的 `pandoc` 检测说法；测试章节、目录结构、已知限制按实际行为重写。
- 修复本地通过但 CI 失败的环境差异：GitHub 运行器的 `TEMP` 是 8.3 短路径（`C:\Users\RUNNER~1\...`），而应用按设计用 `Path.resolve()` 规范化成长路径，测试却按字符串比较 `Path`；`tests/conftest.py` 现在统一使用规范化临时目录。等待后台任务的 5 秒预算在共享运行器上过紧（全局线程池还会排队执行锁屏的 PBKDF2），放宽为 30 秒、启动等待 2 秒改 15 秒。断言本身没有删除、跳过或放宽。

### 4. 预览可逐条编辑，冲突改为跳过（提交 `e182529`）

- 新增 `filemind/core/plan_editor.py`：以不变的计划为基准保存可编辑行，每次修改都重新校验并重建计划；不合法的分类或文件名（例如改动扩展名）会被直接拒绝并说明原因，不会进入计划。
- 预览表新增“执行”列，并把“分类”“建议新文件名”变为可编辑列：双击修改、取消勾选排除某行，目标路径、目录树计数与摘要立即刷新；只有全部行都会被跳过时才禁用执行。
- 目标冲突不再阻断整批：执行器逐条跳过“目标已存在 / 符号链接 / 你排除的行 / AI 批次失败的行”，其余文件照常处理；结果分别报告成功、跳过、失败数量，跳过原因写入操作历史与状态提示。
- 同一分类内出现重名目标时自动追加 `(2)`、`(3)` 后缀，既不覆盖已有文件，也不会因为一个重名让整份计划作废；新增 `requested_name` 区分“用户/AI 请求的名称”和“去重后的实际名称”，避免去重后缀被回写。
- AI 批次失败的行改用行级 `review_note` 标记：编辑其他行不会清除它，只有该行被显式修改后才视为已确认。

### 5. 死代码清理

- 删除 `filemind/conversion/service.py` 中已无人调用的 Qt 图片转换实现（`_image_targets`、`_image_reader`、`_write_image` 及其 Qt 导入）；实际图片转换走 `conversion/images.py` 的 Pillow 路径，这也是 README 原来“本机 Qt 插件支持的目标”失准的原因。
- 清理 11 处未使用的导入（`main_window.py`、`plan_tree.py`、`ai/openai_compatible.py`、`conversion/media.py`、`ui/pages/conversion_page.py`、`ui/pages/settings_page.py`、`ui/styles/icons.py`、`ui/widgets/stat_card.py`、`tools/review_ui.py` 及两个测试文件）。`pyflakes filemind tests tools main.py` 现在完全干净。

### 6. 明确未完成的部分

以下两块按你的要求暂缓，**没有**出现在 `main` 上，代码保存在本地分支 `wip/content-and-recursion`（提交 `ad97292`，未推送）：

- **内容感知分类**：`filemind/ai/content.py` 可对文本、Markdown、代码、CSV/JSON、PDF、DOCX/XLSX/PPTX、EPUB 提取有界正文片段（单文件约 1200 字），随文件名一起发送给 AI，并配套设置页授权开关与隐私说明。
- **递归扫描与性能**：`scan_files(include_subdirectories=...)` 递归扫描、`preserve_relative` 保留原有子文件夹结构、嵌套文件的移动与撤销、AI 分批并行（最多 3 个并发）。

这两块当时已通过全部测试（144 passed），但缺少专门的抽取单测与真实文件验证，因此按你的要求先不纳入。需要时执行 `git merge wip/content-and-recursion` 即可恢复。

### 7. 跨平台适配

- 新增 `filemind/storage/paths.py`：配置与数据目录按平台惯例，Windows 继续用 `%APPDATA%`（配置）与 `%LOCALAPPDATA%`（数据），macOS 统一用 `~/Library/Application Support/FileMind`，Linux 遵循 XDG 规范并支持 `XDG_CONFIG_HOME`/`XDG_DATA_HOME`；四个存储模块（设置、会话历史、工作区偏好、本机锁屏）改为共用这一个实现。目录决策逻辑写成可注入平台的纯函数，五个分支在三平台 CI 上都会被覆盖。
- 中文字体候选按平台展开：Windows（微软雅黑/等线/宋体）、macOS（苹方/冬青黑体）、Linux（Noto Sans CJK/文泉驿/AR PL UMing），并补充了对应家族名回退。
- 本就存在的平台分支经复核保留：凭据存储（非 Windows 返回不可用并回退到环境变量或用户显式选择的明文文件）、DPAPI 记住解锁、系统关联图标、`os.rename` 与 `os.link` 两种移动实现、icacls 与 chmod 0600 两种权限收紧方式。
- 锁屏对话框在缺少 DPAPI 的系统上不再显示"在此 Windows 用户下记住解锁"，改为禁用并说明"当前系统不支持安全记住解锁"，避免给出无法兑现的承诺。
- LibreOffice 探测补充 macOS 应用包、`/usr/lib/libreoffice` 与 snap 路径。
- CI 从单一 Windows 作业改为三平台矩阵，Linux 作业按官方依赖安装 Qt 运行库（libegl1、libxkbcommon-x11、xcb 系列、libfontconfig1 等）与 `fonts-noto-cjk`。

跨平台能力的边界：Windows 仍是主要验证与使用目标；macOS/Linux 上可通过 CI 证明代码路径与界面渲染可用，但没有在真实桌面会话里人工验收过长时间运行、系统托盘、多显示器等场景。“记住解锁 7 天”与系统凭据存储目前只有 Windows 实现。

## 三、如何运行

```powershell
# 1. 首次准备（已在本机完成，换机器时执行）
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 启动应用（正式入口，带本机锁屏）
.\.venv\Scripts\python.exe main.py
```

```bash
# macOS / Linux 等价命令
python3.13 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python main.py
```

首次启动会要求设置本机密码（至少 8 位）并显示一次性恢复码；解锁后才加载工作区。之后在“设置”页填写服务商、Base URL、模型名称和 API Key（密钥默认存进 Windows 凭据管理器），“测试连接”会真实请求服务商并可能产生少量费用。

非 Windows 系统没有可用的系统凭据存储，请在设置页勾选“本机配置文件明文保存”（文件权限 0600）或改用环境变量；解锁页的“记住解锁 7 天”也只在 Windows 上可用。

日常使用的顺序是：选择目录 → 读取文件 → 选择分类方式并填写规则 → 生成建议 → 打开预览逐条核对/修改 → 确认执行 → 在“整理历史”里查看或撤销。

## 四、如何校验

```powershell
# 完整测试套件（预期 141 passed, 24 subtests passed）
.\.venv\Scripts\python.exe -m pytest -q

# 语法编译与依赖一致性
.\.venv\Scripts\python.exe -m compileall -q main.py filemind tests tools
.\.venv\Scripts\python.exe -m pip check

# 静态检查（可选，pyflakes 未列入 requirements）
.\.venv\Scripts\python.exe -m pyflakes filemind tests tools main.py

# 隔离界面检查：只用临时生成的数据，不读取 .env、环境变量密钥、Windows 凭据或真实历史
.\.venv\Scripts\python.exe tools/review_ui.py --page organize --width 1280 --height 850
.\.venv\Scripts\python.exe tools/review_ui.py --page preview --width 1280 --height 850
.\.venv\Scripts\python.exe tools/review_ui.py --page preview --snapshot .artifacts/ui-review/preview.png
```

CI 是最终裁判：任何推送到 `main` 的提交都会在 GitHub 上按 Windows + Python 3.13 重跑上述检查。

手动验收建议关注四点：预览里双击分类/文件名是否被拒绝并给出原因、取消勾选“执行”列后该行是否变为“已排除”、目标已存在时其余文件是否照常移动、以及“整理历史”里成功/跳过/失败的数量与撤销结果。

## 五、验证到什么程度，没有验证什么

已经验证：单元与集成测试在 Windows 本机全绿；`compileall`、`pip check`、`pyflakes` 无告警；用离屏渲染生成了整理页、预览页、Orbit、格式转换、设置、锁屏等界面截图并人工核对；`main.py` 真实启动后停在首次设置界面未崩溃；GitHub Actions 在 Windows、Ubuntu 和 macOS 三个平台上运行同一套检查。

还没有验证：没有发起任何真实模型请求（AI 相关测试全部使用 mock，`测试连接` 需你自己填 Key 后实测）；没有对真实目录执行过整理或撤销；macOS 与 Linux 只由 CI 的自动化测试覆盖，没有在真实桌面会话里人工使用过，也没有测试多显示器、系统缩放或长时间运行；Office 排版转换依赖系统另行安装 LibreOffice，音视频转换依赖 FFmpeg（本项目由 imageio-ffmpeg 自带）。

## 六、已知限制

- 只支持 OpenAI Chat Completions 兼容接口；每个模型与服务商都需用“测试连接”实测。
- 第一版只把元数据作为 AI 输入，无法理解文件正文（正文片段能力在 `wip/content-and-recursion` 分支）。
- 仅处理所选目录第一层，不递归扫描（递归能力同样在未合并分支）。
- 预览可修改分类、分类下的相对子目录和新文件名，不能把某一行移动到任意位置；重名冲突由本地自动追加序号。
- Windows 凭据管理器是推荐密钥存储，明文本地存储只能作为用户明确选择的降级方案。
- 撤销基于文件大小和修改时间检查，无法识别同时恢复这两项属性的内容改写；操作历史写在被整理目录的 `.filemind/history/` 内，目录被移动或改名后历史不会跟随。
- 锁屏是应用级访问提示，不等同于 Windows 账户安全、磁盘加密或防止本机管理员修改程序。

## 七、下一步建议

1. 用你自己的 API Key 跑一次真实的“测试连接”和小目录整理，确认真实模型的分类质量与限速表现。
2. 需要内容理解时，把 `wip/content-and-recursion` 合并回来，先补正文抽取的单测与真实文件验证，再打开界面开关。
3. 目录嵌套场景（真实用户目录往往有多层）属于同一个分支，建议与内容理解一起评估后再合并。
4. 若要长期维护，可把 `pyflakes`（或 ruff）加入 `requirements-dev.txt` 与 CI，让静态检查也自动运行。
