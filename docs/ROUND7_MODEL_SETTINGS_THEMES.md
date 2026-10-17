# 第七轮：补齐模型配置、头像设置与主题

来源为用户提供的 `D:/Development/Project/branch2/FileMind-main`。本轮移植了入口分离、配色和服务商图片，保留当前主项目的目录预览、会话列表、内容识别与转换实现。

## 使用入口

- 左侧 **模型配置**：服务商、API 地址、模型、密钥、连接检测与多模型管理。
- 左下角 **本机用户 → 设置**：外观、本机锁定、修改密码、数据与隐私。
- **Ctrl+,**：通用设置；模型未配置或连接失败时的配置操作仍进入模型配置页。
- 外观支持浅色、深色、跟随系统、绿色、橙色。更改立即生效并保存，重启及锁屏继续使用；绿色、橙色采用浅色背景。
- 保存失败时恢复原选项并展示错误。切换主题不重新加载 API 凭据，不清空未保存模型表单、输入草稿或待发送附件。

## 实现与修改文件

| 文件 | 改动 |
| --- | --- |
| `filemind/storage/settings.py` | 单独读写普通 `appearance` 字段，保留 profiles、models 和其他设置，采用原子写入 |
| `filemind/ui/main_window.py` | 侧栏模型入口、头像设置菜单、独立页面、实时主题与系统主题事件；账户菜单使用透明圆角窗口 |
| `filemind/ui/pages/settings_page.py` | 专注模型设置，为服务商列表添加图标，保留现有保存、检测与多模型逻辑 |
| `filemind/ui/pages/local_settings_page.py`（新增） | 独立外观、锁屏、密码及隐私页面，沿用当前内容识别与并行请求的准确说明 |
| `filemind/ui/styles/theme.py` | 共享配色、Qt 控件调色板、系统色调响应，避免重复设置相同主题 |
| `filemind/ui/styles/palettes.py`（新增） | 基于队友源码整理语义化浅深配色和绿色、橙色强调色 |
| `filemind/ui/styles/base.qss`（新增） | 从原 Python 字符串移出公共 QSS，保持布局与圆角规则 |
| `filemind/ui/styles/orbit.qss`、`conversion.qss`、`models.qss` | 使用语义色值适配深色、卡片、输入框、气泡与弹层 |
| `filemind/ui/styles/icons.py` | 按服务商加载真实图片，深色使用 `ollama_dark.png`，图片缺失时保留矢量回退 |
| `filemind/ui/assets/provider_logos/*.png`（新增） | 用户提供的 13 张服务商图片；原始字节保持不变 |
| `filemind/ui/widgets/model_selector.py` | 添加模型行图标，刷新深浅图标而不重建用户表单 |
| `filemind/ui/widgets/chat_input.py` | 模型图标随主题刷新，保留草稿、附件、模型选择与发送状态 |
| `filemind/ui/widgets/chat_message.py` | Markdown 代码块及引用配色随主题更新，保留已有内容 |
| `filemind/ui/widgets/file_table.py` | 分类、校验与冲突提示使用当前调色板 |
| `filemind/ui/widgets/privacy_dialog.py` | 隐私弹窗使用当前主题 |
| `filemind/ui/widgets/empty_state.py`、`stat_card.py` | 移除固定深色文字，使其继承主题前景色 |
| `filemind/ui/startup.py` | 启动锁屏之前仅读取外观偏好 |
| `tools/review_ui.py` | 增加独立通用设置页隔离预览 |
| `pyproject.toml` | 增加嵌套 PNG 资源打包规则；依赖声明不变 |
| `tests/test_appearance_integration.py`（新增） | 主题持久化、回退、系统响应、导航、图标和未保存状态回归 |
| `tests/test_orbit_ui_polish.py` | 更新设置快捷键目的页，验证扩展服务商列表的滚动与最后一项可达性 |
| `README.md`、`docs/BRANCH2_INTEGRATION.md` | 更新实际入口与整合状态 |

没有新增运行依赖，仍为 Python / PySide6 Qt Widgets / QSS。主题代码来源仓库使用 MIT 许可证；服务商图片由用户随 branch2 提供，只用于识别服务商，品牌标志不因此重新声明为 MIT 授权。

## 验证记录

仅运行本轮新增及受影响的设置、模型管理、聊天外观和头像入口回归，没有重复执行稳定的文件转换/执行器全量测试。

最终定向回归 **48 passed，38.64 秒**：

```powershell
py -3.13 -m pytest tests/test_appearance_integration.py tests/test_model_selector.py tests/test_configuration_flow.py tests/test_orbit_ui_polish.py tests/test_workspace_preferences.py::test_local_menu_lock_and_avatar_are_real_actions -q --tb=short
```

中间一次回归发现旧用例假设服务商列表不滚动，扩展到 13 项后不再成立；已保留透明边缘与圆角断言，并增加滚动到最后一项的可达性检查。初次较大的组合运行因重复应用同一 QSS 耗时偏长而主动停止；修正为相同主题直接复用，并让新增主题用例及时销毁其窗口后，重新运行上述完整定向组合通过。

`py -3.13 -m compileall -q filemind tests/test_appearance_integration.py tools/review_ui.py`、`git -c core.safecrlf=false diff --check` 通过。测试与截图均使用临时生成数据和内存凭据，不读取真实 `.env`、系统密钥、用户聊天或文件内容。

Windows 原生 UI 检查覆盖五种主题的整理、Orbit、转换、历史、模型配置、通用设置；1024×700 与 1280×850 下检查两个设置页，内容宽度未超过视口。服务商弹层保留透明圆角边缘，深色 Ollama 使用白色图标。

构建命令：`py -3.13 -m pip wheel . --no-deps --no-build-isolation --wheel-dir .artifacts/appearance-integration/dist`。成功生成 `filemind-0.1.0-py3-none-any.whl`，并通过 `pip install --no-deps --no-compile --target .artifacts/appearance-integration/installed ...` 安装到隔离目录。

检查 wheel 包含 13 张 PNG、4 份 QSS、独立设置页和调色板模块；打包 UI 文件与当前源码一致，13 张 PNG 与用户提供的源文件逐字节相同。随后运行 `check_ui.py --installed`，断言主窗口模块确实来自安装目录，并完成五种主题和全部页面的 Windows 原生启动、视口与截图检查；服务商和账户菜单左上角透明像素检查通过。本轮不产出 Windows 安装器，也没有修改本机实际 API 配置。

源码修改前备份、截图、原生 UI 脚本、视口测量与 wheel 位于 Git 忽略的 `.artifacts/appearance-integration/`。该目录仅含工程文件和生成示例，不是用户数据备份。

## 追加：修改用户名

头像菜单新增“修改用户名…”，支持 1–32 个字符、首尾空格整理、输入校验、Enter 保存、Esc 取消及保存失败提示。保存后立即更新侧栏和当前/后续聊天中的用户名称；名称仅作为本机显示信息，不加入模型请求、不修改聊天历史。长名称在侧栏省略显示，完整名称保留在提示和无障碍名称中。

修改文件：

- `filemind/storage/workspace.py`：新增 `user_name` 偏好与校验，兼容旧配置，原子保存并保留其他偏好。
- `filemind/ui/dialogs/user_name.py`（新增）：沿用当前 QSS 的用户名编辑弹窗。
- `filemind/ui/widgets/local_account.py`：增加可省略长用户名的账户按钮。
- `filemind/ui/main_window.py`：连接修改用户名菜单、保存后的即时同步与启动时恢复。
- `filemind/ui/pages/assistant_page.py`、`filemind/ui/widgets/chat_message.py`：当前和后续消息使用纯文本用户名，保留 Orbit 名称。
- `filemind/ui/styles/models.qss`：输入错误提示配色。
- `tests/test_user_name.py`（新增）：本机保存、旧配置、校验、取消、错误、同步、重启与窄窗口回归。
- `tests/test_workspace_preferences.py`、`tests/test_orbit_ui_polish.py`：按菜单含义与用户消息角色查找控件，验证新增用户名下原头像/锁定行为。
- `README.md`：补充入口与本机保存说明。

新增依赖：无。定向测试共 14 项通过：用户名和账户菜单 12 项（13.83 秒），原头像与消息显示 2 项（8.72 秒）；相关 Python 编译及 Git 空白检查通过。Windows 原生 Qt 下通过真实菜单打开模态弹窗，验证浅/深色、空名禁用、保存、长名省略和 1024×700 布局。脚本与截图在 `.artifacts/user-name/`。wheel 已重新构建以包含新增对话框。
