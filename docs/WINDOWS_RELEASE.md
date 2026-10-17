# Windows 打包与 GitHub 发布

> 正式发布请使用 [统一 Windows 发布流程](RELEASE_PIPELINE.md)，包含 onedir spec、依赖锁、版本资源、中文安装向导及 GitHub 工作流。下面保留早期手工命令供参考。

图标已接入源码，PyInstaller 和 Inno Setup 构建由你自行执行。本次没有运行这两个打包程序，也没有上传或创建 GitHub Release。

## 1. 准备构建环境

在 Windows x64 上使用 Python 3.13。以下全部为 **PowerShell** 命令，在同一个终端按顺序执行。先提交准备发布的源码；不要把 `.env`、用户配置、聊天数据或凭据拷入发布目录。

```powershell
Set-Location "D:\Development\Project\FileMind"
py -3.13 -m venv .venv-build
$python = ".\.venv-build\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt
& $python -m pip install "pyinstaller==6.21.0" "pyinstaller-hooks-contrib==2026.6"
& $python -c "import platform, struct; print(platform.python_version(), platform.machine(), struct.calcsize('P') * 8)"
```

最后一行应显示 Python 3.13、AMD64 与 64。这里固定的打包工具版本与本机已经安装的版本一致，未宣称已完成 EXE 构建验证。构建工具只装入 `.venv-build`，不加入应用运行依赖。

## 2. PyInstaller 生成应用目录

采用 `onedir` 目录模式，再交给 Inno Setup 制作一个安装 EXE。图标、QSS、服务商图片、PDFium 和 FFmpeg 的包内文件需要一起收集。参数参考 [PyInstaller 官方用法](https://pyinstaller.org/en/stable/usage.html)。

```powershell
& $python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onedir `
  --noupx `
  --name FileMind `
  --icon ".\filemind\ui\assets\FileMind_AppIcon.ico" `
  --add-data ".\filemind\ui\assets:filemind/ui/assets" `
  --add-data ".\filemind\ui\styles:filemind/ui/styles" `
  --add-data ".\LICENSE:." `
  --collect-data docx `
  --collect-data pptx `
  --collect-submodules fontTools `
  --collect-all pypdfium2 `
  --collect-all pypdfium2_raw `
  --collect-all imageio_ffmpeg `
  ".\main.py"

if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，请检查上方错误。" }
```

PowerShell 的续行符是反引号，每行末尾的反引号后面不能有空格。整个输出目录是应用：

```text
dist/
  FileMind/
    FileMind.exe
    _internal/
      ...Python、Qt、QSS、图标和转换依赖...
```

先自行运行：

```powershell
& ".\dist\FileMind\FileMind.exe"
```

核对锁屏/窗口/任务栏图标、设置保存，以及你准备发布的图片/PDF/音视频转换能力。目录模式需要保留 `_internal`；不要只复制 `FileMind.exe`。LibreOffice、Ollama 等外部程序不会由上述命令安装；相关功能继续按目标电脑的实际环境检测。

## 3. Inno Setup 生成安装包

已提供 `packaging/FileMind.iss`。使用 Inno Setup 6.3 或更新版本。脚本采用 `x64compatible`，解释见 [官方架构说明](https://jrsoftware.org/ishelp/topic_setup_architecturesallowed.htm)。安装界面使用内置英文语言文件，无需另行下载翻译。

### 用界面亲自操作

1. 先完成第 2 节，确认 `dist/FileMind/FileMind.exe` 存在，并能自行启动。没有这个文件时，脚本会提示先运行 PyInstaller。
2. 打开 **Inno Setup Compiler**，选择 **File → Open**，打开项目中的 `packaging/FileMind.iss`。如果启动时弹出欢迎窗口，选择打开已有脚本。
3. 查看开头的 `#define AppVersion "0.1.0"`，将它与 `filemind/__init__.py` 的版本保持一致。第一次可直接用 `0.1.0`。`AppId` 是升级识别标识，后续版本也保持不变。
4. 保存脚本，点击 **Compile（编译）**。图标和输入目录已经设置好，无需再走新建安装向导。等待下方编译日志完成，若出错先看第一条报错。流程参考 [Inno Setup 官方说明](https://jrsoftware.org/ishelp/topic_creatinginstallations.htm)。
5. 成功后在 `dist/installer/` 找到 `FileMind-Setup-0.1.0-x64.exe`（文件名跟随版本号）。双击该文件，亲自完成安装、启动、桌面快捷方式及卸载检查。

### 或使用命令行

- 安装位置：当前用户 `%LOCALAPPDATA%\Programs\FileMind`，无需管理员权限。
- 开始菜单快捷方式，桌面快捷方式可选。
- EXE、Setup、卸载入口和快捷方式引用统一图标。
- 升级时保留相同 `AppId`；不要每次发布修改它。
- 卸载仅处理安装文件，保留原本位于用户数据目录的用户名、设置、历史及头像。

将 `$iscc` 改成你实际安装的路径，例如安装在 devtools 时使用 `D:\devtools\Inno Setup 6\ISCC.exe`。以下默认路径来自常见安装位置；没有检测到本机可直接调用的 ISCC，不将其当作已安装事实。

```powershell
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path -LiteralPath $iscc)) { throw "请将 `$iscc 改为实际 ISCC.exe 路径。" }
$version = & $python -c "import filemind; print(filemind.__version__)"
if ($LASTEXITCODE -ne 0) { throw "无法读取应用版本。" }

& $iscc "/DAppVersion=$version" ".\packaging\FileMind.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败，请检查上方错误。" }
```

`/DAppVersion` 是 [Inno Setup 命令行预处理定义](https://jrsoftware.org/ishelp/topic_compilercmdline.htm)，图标参数见 [SetupIconFile](https://jrsoftware.org/ishelp/topic_setup_setupiconfile.htm)。源码版本当前来自 `filemind/__init__.py` 的 `__version__`；例如 `0.1.0` 生成：

```text
dist/installer/FileMind-Setup-0.1.0-x64.exe
```

自行试装、启动和卸载一次，再用于正式发布。若资源管理器或已固定的旧快捷方式仍显示旧图标，可先取消固定，再从新安装位置重新固定；以新构建 EXE 自带的图标为准。

## 4. 发布到 GitHub Releases

安装包放到 Releases 资产，源码及图标放 Git 仓库。构建目录已被 `.gitignore` 排除，不需要把运行库和安装包提交进源码历史。

可另行把应用整个目录打成便携 ZIP，并生成安装包校验值：

```powershell
$installer = ".\dist\installer\FileMind-Setup-$version-x64.exe"
$portable = ".\dist\FileMind-$version-win-x64.zip"
Compress-Archive -Path ".\dist\FileMind" -DestinationPath $portable -Force
$checksum = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$checksum  $(Split-Path -Leaf $installer)" | Set-Content -Path "$installer.sha256" -Encoding ascii
```

在已配置好目标 GitHub 仓库、提交并推送发布源码后，以下命令由你执行。`git tag` 给当前提交打标签；不要在未提交的修改上直接发布：

```powershell
git tag "v$version"
git push origin "v$version"
gh release create "v$version" $installer $portable "$installer.sha256" `
  --verify-tag --title "FileMind $version" --generate-notes
```

需要 GitHub CLI 并登录自己的账户，参数见 [gh release create 官方说明](https://cli.github.com/manual/gh_release_create)。也可以在 GitHub 网页 Releases → Draft a new release 中选择标签，上传同样三个文件。

## 本轮工程修改

- `filemind/ui/assets/FileMind_AppIcon.ico`、`.png`、`.svg`：用户提供的三份原始文件，原样复制。
- `filemind/ui/branding.py`：共用应用图标、版本、显示名称与 Windows 任务栏标识。
- `filemind/ui/startup.py`、`main_window.py`、`dialogs/local_lock.py`：启动、主窗口、侧栏与锁屏使用统一图标。
- `filemind/ui/styles/base.qss`：移除旧 FM 字母底板，使品牌标识展示原图。
- `packaging/FileMind.iss`：相对路径的 Inno Setup 脚本，不含本机开发目录。
- `.gitignore`：排除构建虚拟环境。
- `tests/test_app_icon.py`：图标尺寸、PNG 回退、界面接入及安装配置引用的定向验证。

应用运行依赖不变。本轮未执行 PyInstaller、ISCC 或 GitHub 发布操作；生成 EXE、安装包及其实际运行结果由你执行上述流程确认。
