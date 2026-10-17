# 第四轮：Orbit 与转换页 UI 验收

日期：2026-10-16。保留 Python 3.13 + PySide6 Qt Widgets，未新增依赖、修改构建配置或更改模型请求协议。本轮开始时工作区已有上一轮及模型目录迁移的修改，均保留。

## 实际问题与修复

### 下拉菜单方框

复现截图后检查实际对象，展开的列表仍使用 `QComboMenuDelegate` 和 `QComboBoxPrivateContainer`。关闭控件的圆角绘制没有覆盖展开后的原生菜单选中框与外层面板。即使将 frameShape 设为 NoFrame、lineWidth 设为 0，实际截图仍出现灰色外矩形。

新增 `widgets/combo_box.py`：继续使用 QComboBox 的数据模型、当前索引和信号，通过自有透明无框弹窗绘制单层圆角轮廓；列表使用圆角选中态代理，不绘制系统焦点矩形。模型、整理预设、整理模式、服务商和转换目标共用此组件。

实测弹窗四角 alpha 为 0，模型单项菜单及六项整理预设完整显示。覆盖鼠标选择、方向键、Enter、Escape、空格展开，以及控件禁用/隐藏时关闭菜单。未增加虚假的可选模型，API ID 与配置切换逻辑不变。

### Orbit 聊天

- 独立的 Orbit 圆形矢量头像与用户头像，显示“Orbit / 你”身份。
- 复用本机账户头像，更换后立即更新已有与后续用户消息；头像不写进消息数据，也不发送给 AI。
- 清爽浅色背景、浅蓝用户气泡、白色 AI 消息和蓝色发送按钮。将重复页面样式集中到 `styles/orbit.qss`，复用主题色。
- 保留 Markdown、安全图片资源拦截、长消息按真实宽度重排和外层滚动；附件名称强制纯文本显示。
- Enter 发送、Shift+Enter 换行，新增输入法预编辑保护，候选确认不提前发消息。
- 字体已存在时直接使用，避免每次应用主题都重复注册系统字体。

### 设置入口

移除每页右上角的“模型设置”。保留侧栏设置、Ctrl+,、未配置模型及请求错误时的上下文引导。真实窗口激活后快捷键进入设置通过键盘测试。

### 转换页

- 文件名旁新增 × 清除选择，清空旧目标、输出位置和结果引用，恢复初始引导。
- 不删除源文件与已生成输出；运行中禁用清除，先取消并等待任务停止后再操作，避免后台旧结果重新写回界面。
- 识别完成后重置等待进度条；仅运行或已完成转换时显示进度，取消按钮仅运行时显示。
- 彩色格式卡仅列出已安装后端可用的类别，不再展示不可用 Office 排版、OCR、RAW/HEIC 等未启用功能说明。目标选择和必要的格式限制继续由真实适配器提供。

## 修改文件

| 文件 | 变化 |
| --- | --- |
| filemind/ui/widgets/combo_box.py | 共享自有弹层、选中行代理、键盘和关闭生命周期 |
| filemind/ui/widgets/chat_message.py | 头像、身份、消息排版、纯文本附件名 |
| filemind/ui/widgets/chat_input.py | 复用弹层、中文输入法保护 |
| filemind/ui/widgets/local_account.py | 更清晰的默认高分辨率头像图标 |
| filemind/ui/pages/assistant_page.py | 用户头像更新、移除重复局部样式 |
| filemind/ui/pages/organize_page.py、settings_page.py | 复用共享下拉菜单 |
| filemind/ui/pages/conversion_page.py | 清除选择、进度状态、共享下拉菜单 |
| filemind/ui/main_window.py | 收敛设置入口、同步账户头像 |
| filemind/ui/styles/orbit.qss | 集中聊天样式 |
| filemind/ui/styles/theme.py、icons.py | 主题加载、字体复用、弹层样式、Orbit 矢量图标 |
| filemind/conversion/capabilities.py | 仅返回可用类别，精简说明 |
| tests/test_orbit_ui_polish.py | 新增控件、键盘、头像、取消及能力过滤验证 |
| README.md、本文件 | 使用和验收记录 |

## 实际验证

基线：`py -3.13 -m pytest -q`，175 passed、24 subtests passed，149.77 秒。

阶段验证：聊天布局、转换流程、既有 UI 集成、设置和工作区测试通过。新增测试最初发现快捷键测试在窗口尚未激活时发送键盘事件，改为先激活并检查真实焦点；保留打开设置的行为断言。

完整回归：`py -3.13 -m pytest -q`，192 passed、24 subtests passed，266.73 秒；相比基线增加 17 项测试，未删除、跳过或降低原测试断言。

编译及导入：`py -3.13 -m compileall -q main.py filemind tests tools` 通过；主窗口和新组件导入通过；新功能函数不超过 50 行。`py -3.13 -m pip check` 返回 No broken requirements found。

实际 Windows Qt 启动检查 1024×700、1280×850：欢迎页、聊天页、模型聚焦/展开/Enter 选中、预设弹层、转换空态/选择/清除；菜单四角透明，无额外灰矩形，六项预设无裁切或多余滚动。截图保存在 `.artifacts/ui-review/round4/`，对话、文件和模型显示均为临时验收数据，没有发起真实模型请求或读取用户密钥。

## 范围与限制

现有文件扫描、安全计划、预览确认、执行、历史和撤销继续由原模块处理。本轮未改变模型 API 配置、隐私确认或附件发送行为。头像仍仅保存在本机。

未覆盖所有 Windows 主题、多显示器切换及屏幕阅读器组合；菜单保留实际鼠标和键盘选择测试。真实模型连通性不由 UI mock 或截图证明。未新增第三方代码或依赖。
