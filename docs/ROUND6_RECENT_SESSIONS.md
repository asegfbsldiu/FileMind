# 第六轮：按日整理与 Orbit 最近对话

验收日期：2026-10-17。延续 Python 3.13、PySide6 Qt Widgets 与现有 QSS；本轮没有新增依赖、迁移框架或改动模型连接。保留工作区原有 Claude、队友与前几轮修改。

## 完成内容与原因

### 本地按年月日整理

原预设实际使用 `%Y-%m`，因此只生成按月目录。现在界面显示“按修改年月日 · 本地”，新预设键为 `modified_day`，按本机时区的修改时间产生 `YYYY-MM-DD` 目录，例如 `2026-02-03`。保留旧 `modified_month` 分类入口的原有含义，避免已有调用失效。

日期分类仍只读取元数据，不理解内容、不自动改名。生成计划后仍需预览和明确确认，才会进入现有安全执行流程。

### 最近对话空间与样式

源码没有按“两天”筛选记录的逻辑；列表被导航区、永久伸缩留白挤压，显示空间不足。现在导航区采用紧凑行高和独立滚动；最近对话占用剩余空间，最小区域高度 280px。只有空状态或离开 Orbit 时才放置相应留白，账户入口保持在侧栏底部。

- 对话行统一为 52px，包含矢量图标、标题、活动时间和消息数量。
- 长标题省略显示，提示中可查看完整标题；按标题搜索，不删除或改写记录。
- 标题旁显示总数，搜索时显示匹配数/总数；没有记录或匹配结果时显示空状态。
- 选中、悬停和更多操作沿用紫蓝主题，样式集中在 `orbit.qss`。
- 方向键选择会话后可按 Enter 打开；搜索、新建与更多按钮提供圆角焦点反馈。
- 本地记录容量由 50 段增加至最近 200 段，不按日期过期。超过容量时沿用原来的最旧记录裁减机制；已被过去版本裁减或手动删除的记录不能恢复。

### 删除菜单圆角

原实现使用 `QMenu`：QSS 只能修饰内部菜单，Windows 的外层原生菜单窗口/阴影仍可能显示矩形边缘。现在删除操作复用模型选择器的 `ComboPopup` 和圆角项目委托，使用无边框、无原生阴影、透明四角的单层绘制表面。

菜单按需创建，不为 200 个对话提前创建 200 个弹层窗口。支持点击、Enter 执行、Escape 退出，隐藏对话行时同步关闭弹层。点击删除后仍由主窗口询问确认，拒绝时不删除，只删除明确选中的记录。

## Qt 生命周期回归

组合测试中复现过退出异常：`QApplication.topLevelWidgets()` 包含有父控件的 `Qt.Popup`；测试清理同时对父窗口和弹层调用 `deleteLater()`，顺序不确定，组合框的 `hideEvent()` 可能访问先被销毁的弹层。

清理改为只销毁没有父对象的根窗口，让 Qt 按所有权释放子控件。保留后台线程等待、延迟销毁事件处理和垃圾回收。没有移除测试或降低断言；另加用例确认销毁父窗口会释放模型与删除弹层。

## 修改文件

| 文件 | 改动 |
| --- | --- |
| `filemind/core/organization_presets.py` | 按日预设与旧按月入口兼容 |
| `filemind/ui/pages/organize_page.py` | 本地能力说明更新为年月日 |
| `filemind/storage/chat_history.py` | 容量增加至 200 段 |
| `filemind/ui/main_window.py` | 侧栏空间分配、搜索、数量、两行会话布局 |
| `filemind/ui/widgets/conversation_row.py` | 图标、时间、标题省略及复用圆角删除弹层 |
| `filemind/ui/styles/icons.py` | 搜索、加号、垃圾桶矢量图形 |
| `filemind/ui/styles/orbit.qss` | 导航、对话行、搜索与按钮交互样式 |
| `tests/test_organization_workspace.py` | 原日期分类用例更新为完整日期断言 |
| `tests/test_recent_sessions.py`（新增） | 日期、容量、布局、搜索、菜单、确认与生命周期回归 |
| `tests/conftest.py` | 按 QObject 所有权清理测试窗口 |
| `README.md`、本文 | 使用与验收记录 |

## 实际验收

Windows 原生 Qt 平台启动，使用隔离配置与生成的 40 段会话，没有加载真实聊天记录、密钥或凭据。

| Qt 逻辑窗口尺寸 | 最近对话高度 | 完整可见行数 | 侧栏宽度 |
| --- | --- | --- | --- |
| 1024×700 | 300px | 4 | 252px |
| 1280×850 | 450px | 7 | 252px |
| 1024×700，额外增加 10 个导航项 | 280px | 列表独立滚动 | 252px |

检查了滚动至最旧记录、搜索/清空搜索、无匹配、空记录、长标题省略、新建、取消删除、确认删除、Escape 关闭菜单、日期预设下拉和全部现有页面导航。删除弹层透明角像素检查通过，截图也已目视检查。

截图与原生验收脚本位于本地忽略目录 `.artifacts/round6/`：`sidebar-1024.png`、`sidebar-1280.png`、`search.png`、`search-empty.png`、`empty-history.png`、`delete-popup.png`、`date-presets.png`、`expanded-navigation.png`。脚本只写临时生成记录，可用 `py -3.13 .artifacts/round6/check_ui.py` 复现。

测试与静态检查：

- `py -3.13 -m pytest tests/test_organization_workspace.py tests/test_workspace_layout.py tests/test_workspace_preferences.py -q --tb=short`：16 项通过。
- `py -3.13 -m pytest tests/test_recent_sessions.py tests/test_orbit_ui_polish.py -q --tb=short`：27 项通过（当时尚未加入最后一个生命周期回归用例）。
- `py -3.13 -m pytest tests/test_recent_sessions.py -q --tb=short`：包含 Enter 打开会话的新增回归 11 项通过，13.95 秒。
- `py -3.13 -m pytest -q --tb=short`：首轮完整回归 281 项测试与 24 项子测试通过，562.17 秒。之后补齐键盘 Enter 操作，相关 11 项回归通过（见上一条）。第二轮重复全量运行按用户“减少稳定模块重复测试”的要求中止，不计作完整通过结果。
- `py -3.13 -m compileall -q main.py filemind tests tools`：通过。
- `py -3.13 -m pip check`：`No broken requirements found.`。
- `git diff --check`：无空白错误；Git 对原有部分文件提示 LF/CRLF 转换，不涉及编译失败。

## 限制

会话数取决于已有本地记录；本轮不生成虚假历史填充用户列表，也不恢复已删除记录。搜索仅匹配标题。没有进行真实模型请求，本轮测试通过不表示 API 已连接。

后续采用与改动范围匹配的验证：优先测试受影响模块及相邻交互；只有涉及共享基础设施、数据安全或多模块回归时再扩大范围，避免反复运行稳定的转换等无关用例。
