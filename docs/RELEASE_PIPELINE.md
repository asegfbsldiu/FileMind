# FileMind 正式 Windows 发布流程

当前维护工程：`D:\Development\Project\FileMind`。模式固定为 **PyInstaller onedir + Inno Setup**，从其他目录调用脚本也能正确定位资源。克隆到其他位置后，在实际仓库根目录执行即可。

## 工程来源

- 发布配置最初在本机 `FileMindBuild` 副本中准备，现已逐项整合回本仓库，保留原 `.git` 历史与 `master` 分支。
- 原有应用功能、图标、QSS 和业务测试保留；新增发布脚本、离线自检、中文安装向导和工作流。
- `SOURCE_SNAPSHOT.json` 记录最初复制时的源码基线及后续图标刷新。它用于来源核对，不是当前源码的完整清单，也不限制以后改进代码或测试。
- 后续以本仓库维护源码和发布配置。旧 `FileMindBuild` 是本机副本，与本仓库不会自动同步；其 `.git`、虚拟环境及构建产物不参与整合。
- 正常启动使用 FileMind 的标准用户目录。首次安装体验可在新 Windows 用户或虚拟机中检查。发布自检使用生成数据，不读取真实账号、密钥或聊天。

## 配置文件

| 文件 | 用途 |
| --- | --- |
| `scripts/build-windows.ps1` | Prepare / Bundle / Installer / All 四阶段命令，失败立即退出 |
| `packaging/FileMind.spec` | 固定 onedir、无控制台、图标、Qt/QSS、转换后端及模板 |
| `packaging/FileMind.iss` | 当前用户安装、稳定 AppId、统一图标、快捷方式、卸载入口 |
| `packaging/requirements-windows.lock` | Windows / Python 3.13 的 32 个运行依赖及传递依赖固定版本 |
| `packaging/requirements-build.lock` | 12 个构建/测试工具及其依赖固定版本 |
| `tools/windows_release.py` | 版本资源、依赖许可、冻结包验证、ZIP、清单与 SHA256 |
| `tools/export_app_icon.py` | 从可编辑 SVG 重新导出透明 PNG 和七档 Windows ICO |
| `tools/export_installer_art.py` | 安装器紫蓝侧栏、页眉图标及保留 MIT 原文的中文许可说明 |
| `packaging/installer/` | 高 DPI BMP 品牌素材及安装器许可页文本 |
| `filemind/release_check.py` | EXE 离线自检，临时生成图片/PDF/Office 样本，不调用模型 |
| `.github/workflows/release-windows.yml` | Windows 构建、产物上传和 GitHub 草稿 Release |

spec 中的 `Analysis` / `EXE` / `COLLECT` 及资源路径遵循 [PyInstaller 官方文档](https://pyinstaller.org/en/stable/spec-files.html)。不要在 spec 模式下追加 `--onefile` 或尝试用命令行覆盖图标等已固定选项。

## 1. 校验配置与准备环境

需要 Windows x64、Python 3.13 x64、PowerShell 和 **Inno Setup 6.5 或更新版本**。简体中文语言文件随项目保存在 `packaging/installer/languages/ChineseSimplified.isl`，使用固定上游版本并保留来源与许可证；编译机无需额外安装语言包。Inno Setup 可以继续装在你的 `D:\devtools` 目录。

在 PowerShell 中执行：

```powershell
Set-Location "D:\Development\Project\FileMind"

# 只校验配置：不安装依赖，不运行 PyInstaller / Inno Setup
.\scripts\build-windows.ps1 -ValidateOnly

# 创建 .venv-build，安装两个 lock 文件，生成版本和许可证资料
.\scripts\build-windows.ps1 -Stage Prepare
```

如果本机执行策略阻止脚本，可只对本次进程执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1 -Stage Prepare
```

`Prepare` 不生成 EXE，也不修改全局 Python 环境。源依赖声明仍在 `requirements.txt`，锁定结果单独保存，变更依赖后要审阅并更新锁文件；不要直接把整台机器的 `pip freeze` 放入发布工程。

本工程的 PNG / ICO 已从透明背景 SVG 重新导出，保留原图形。以后修改 SVG，可运行 `.\.venv-build\Scripts\python.exe tools\export_app_icon.py` 刷新导出文件，再提交并打包。

## 2. PyInstaller 构建文件夹版

```powershell
.\scripts\build-windows.ps1 -Stage Bundle
```

此阶段从 `filemind/__init__.py` 读取唯一版本号，生成 Windows EXE 版本资源和 Inno include；随后使用 spec 构建并运行真正的 EXE 自检。

```text
dist/FileMind/
  FileMind.exe
  _internal/
    filemind/ui/assets/...
    filemind/ui/styles/...
    THIRD_PARTY_NOTICES.txt
    THIRD_PARTY_LICENSES/...
    ...Python、Qt、PDFium、FFmpeg 等依赖...
```

自检报告位于 `build/release/self-check.json`。要求 `ok: true`、`frozen: true`，且版本与源码相同。检查包含 Qt、图标/QSS、DOCX/PPTX 模板、XLSX、PNG/PDFium、WOFF2/Brotli 和实际打入包内的 FFmpeg；不把开发机 PATH 中的 FFmpeg 当作打包成功。

想先看源码自检，可自行运行：

```powershell
.\.venv-build\Scripts\python.exe main.py --self-check --report build\release\source-check.json
```

源码报告标记 `frozen: false`，不能替代 EXE 自检。正常启动仍走原锁屏入口：

```powershell
& .\dist\FileMind\FileMind.exe
```

LibreOffice、Ollama 等外部程序不被自动安装，对应功能继续按目标电脑的实际环境显示。

## 3. 亲自操作 Inno Setup

`Bundle` 通过后：

1. 打开 **Inno Setup Compiler**，选择 **File → Open**。
2. 打开本工程的 `packaging/FileMind.iss`。
3. 版本默认从 `build/release/metadata.iss` 读取，不维护第二份版本号。
4. 点击 **Compile**，等待成功。
5. 在 `dist/installer/` 找到 `FileMind-Setup-0.1.0-x64.exe`，名称跟随实际版本。

流程参考 [Inno Setup 官方说明](https://jrsoftware.org/ishelp/topic_creatinginstallations.htm)。现在采用截图中的六步中文安装向导：

1. **欢迎**：紫蓝品牌侧栏、现有 FileMind 图标与欢迎文案。
2. **许可协议**：中文阅读提示和完整 MIT 原文，点击“我同意”继续。
3. **选择安装位置**：浏览目录，空间需求由实际安装文件计算。
4. **附加任务**：桌面快捷方式默认勾选；开机自动启动默认关闭，可独立选择。点击“安装”开始。
5. **安装进度**：原生进度条显示实际文件复制过程，可取消。
6. **完成**：品牌侧栏和可选的“启动 FileMind”。

安装界面使用微软雅黑 UI，品牌图提供四倍分辨率。字标保存在 `packaging/installer/wordmark.svg` 中，文字已转为矢量轮廓，构建机无需额外安装字标字体。`Prepare`、`Bundle`、`Installer` 阶段会自动刷新品牌图及许可页；也可单独执行 `.\.venv-build\Scripts\python.exe tools\export_installer_art.py`。更换图标后先更新应用图标导出，再重新打包。

图标、开始菜单、卸载入口和 Windows AppUserModelID 一致。默认给当前用户安装到 `%LOCALAPPDATA%\Programs\FileMind`，无需管理员权限；可通过“浏览”改到自己有写权限的目录。后续升级保持 `AppId` 不变。取消勾选附加任务时，只清理对应的 `FileMind.lnk` 快捷方式；不编写删除用户数据的卸载规则。

GUI 编译完成后，生成便携 ZIP 和校验清单：

```powershell
.\.venv-build\Scripts\python.exe tools\windows_release.py artifacts
```

也可自行运行命令行编译，自动生成同样产物：

```powershell
.\scripts\build-windows.ps1 -Stage Installer -IsccPath "D:\devtools\Inno Setup 6\ISCC.exe"
```

不传 `-IsccPath` 时，会在 PATH、Program Files 和 `D:\devtools\Inno Setup*` 下查找。编译器版本记入发布清单；GUI 手动编译记为 `manual GUI build`。

## 4. 一条命令执行全部阶段

准备好实际打包时再运行：

```powershell
.\scripts\build-windows.ps1 -Stage All -IsccPath "D:\devtools\Inno Setup 6\ISCC.exe"
```

此命令会更新本工程的 `.venv-build`、`build` 和 `dist`。

## 5. 最终发布文件

```text
dist/release/0.1.0/
  FileMind-Setup-0.1.0-x64.exe
  FileMind-0.1.0-win-x64.zip
  release-manifest.json
  FFMPEG-LICENSE.txt
  SHA256SUMS.txt
```

ZIP 包含完整 `FileMind` 目录，不要只分发单个 EXE。不同版本分别输出，避免混入旧版本产物。清单记录版本、运行依赖、PyInstaller/hooks、编译器和真正 EXE 自检结果。`SHA256SUMS.txt` 对前四个文件计算校验值。

尚未配置代码签名，因此不称这些 EXE 为已签名程序；如需签名，后续单独配置自己的证书和时间戳服务。本轮不读取本机证书私钥。

## 6. GitHub Actions / Releases

继续使用本仓库原有的 `origin` 和 `master` 分支提交、推送。源码和发布配置提交 Git，`.venv-build`、`build`、`dist` 不提交。业务 CI 监听 `master` 与 `main`；普通源码推送不会自动创建安装包 Release。

- **只构建**：Actions → Windows Release → Run workflow，保持 `create_draft_release` 关闭。成功后下载 `FileMind-windows-x64` artifact。
- **生成草稿**：修改 `filemind/__init__.py` 中的版本，提交并推送，然后推送对应 `vX.Y.Z` 标签。
- 标签必须和源码版本一致，否则失败。
- 手动勾选 `create_draft_release` 时，也必须在 Run workflow 中选择匹配的版本标签。
- 只创建/更新草稿，最终由你点击 Publish release；已发布版本不会被自动覆盖。

```powershell
# 在已提交、已配置 origin 并推送源码的前提下执行
git tag v0.1.0
git push origin v0.1.0
```

构建在 `windows-2022` 运行，固定 Python 3.13 x64；安装锁定依赖和 Inno Setup，执行发布专用测试、PyInstaller、自检、安装器和清单生成。构建 job 只有读取权限，草稿 Release job 才有写权限。自动 token 仅用于该 job，不需要把个人 token 写入源码。

工作流使用官方 [upload-artifact](https://github.com/actions/upload-artifact)、[download-artifact](https://github.com/actions/download-artifact) 和 [GitHub CLI Release](https://cli.github.com/manual/gh_release_create)。原业务 CI 和全部测试保留；发布工作流只增加受本流程影响的定向测试。

## 7. 许可与实际验证范围

实际运行依赖的名称、版本和许可证复制到包内；FileMind 自有源码的 MIT 许可不会重新授权 Qt、PDFium、FFmpeg 或服务商标志。参考 `packaging/licenses/README.md`。

发布流程使用现有应用运行依赖，发布环境另行锁定以下主要工具，完整传递依赖在 `packaging/requirements-build.lock`：

| 工具 | 版本 | 用途与许可 |
| --- | --- | --- |
| PyInstaller | 6.21.0 | onedir / Windows 资源；GPLv2-or-later，含允许分发构建结果的特殊例外 |
| pyinstaller-hooks-contrib | 2026.6 | 依赖收集；标准 hook 为 GPL-2.0-or-later，运行时 hook 为 Apache-2.0 |
| pytest | 9.0.2 | 发布定向测试；MIT |

PyInstaller 和 hooks 的实际许可证也复制到 `THIRD_PARTY_LICENSES/build-tools/`，覆盖随应用分发的 bootloader / runtime hook 许可说明。

本机当前附带的 FFmpeg 二进制声明为 GPLv3 或更新版本。流程附带原文并保存实际输出；公开分发时仍需按 [FFmpeg 官方说明](https://ffmpeg.org/legal.html) 处理对应源码等要求。Qt/PySide6 按其实际许可处理。

提交发布配置前可执行以下定向验证：

```powershell
.\.venv-build\Scripts\python.exe -m pytest tests/test_windows_release.py tests/test_installer_wizard.py tests/test_app_icon.py -q --tb=short
.\.venv-build\Scripts\python.exe main.py --self-check --report .artifacts\release-validation\source-self-check.json
```

源码自检报告明确标记 `frozen: false`。实际安装、卸载、不同 DPI 的布局和 GitHub Actions 结果，需要分别在 EXE 构建、安装体验和工作流运行后确认。

## 8. 中文安装向导修改清单

- `packaging/FileMind.iss`：六个中文页面、“我同意”按钮、附加任务、原生进度及完成后启动。
- `packaging/installer/wizard-sidebar.bmp`、`wizard-small.bmp`：现有紫蓝图标和品牌侧栏，四倍分辨率。
- `packaging/installer/wordmark.svg`：字标及中文标语的矢量轮廓，避免构建时缺少字体产生方框字。
- `packaging/installer/LICENSE.zh-CN.txt`：中文阅读提示、第三方许可位置及完整原始 MIT 许可。
- `tools/export_installer_art.py`：从 SVG 生成安装器素材和许可文本。
- `scripts/build-windows.ps1`：各阶段刷新安装器素材，提示 Inno Setup 6.5+。
- `tools/windows_release.py`：检查安装器必要输入完整性。
- `tests/test_installer_wizard.py`：六项向导/素材/许可检查。
- `tests/test_windows_release.py`：更新生成测试工程的安装器输入。
- `.github/workflows/release-windows.yml`：增加安装向导定向测试。
- `docs/RELEASE_PIPELINE.md`：更新实际页面、默认选项、最低编译器版本和操作步骤。

安装器素材包含已转为轮廓的中文字标；定向测试检查页面配置、默认选项、许可原文、素材尺寸、字标像素和重复生成的一致性。实际安装窗口布局及不同 DPI 下的呈现应在编译后检查。
