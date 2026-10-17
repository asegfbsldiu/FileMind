# 队友分支整合记录

日期：2026-10-16。来源为同级 `branch/FileMind` 仓库的 `179f2c7`，共同基线为 `a89fb90`。按模块移植经过审阅的改动，保留当前工作区已有的 models 包、聊天头像、圆角弹层、转换清除及其他未提交修改。

## 采用的改动

- 计划编辑器：独立管理分类、相对子目录、建议文件名和排除状态；每次修改重新校验。预览表支持双击编辑分类、新文件名，以及逐条勾选执行。
- 计划内重名追加序号；磁盘上已存在的目标不覆盖，按行跳过。未确认的 AI 失败行、排除行和带校验警告的行同样跳过；其余安全行须经二次确认后才能执行。
- 操作记录新增跳过状态和原因。历史页及底部摘要显示成功、跳过、失败；撤销仅处理实际成功的移动。
- 共用跨平台目录规则，扩展字体与 LibreOffice 探测；无 DPAPI 的系统明确禁用记住解锁。Windows 正常配置路径保持不变。
- 加入 setuptools 安装元数据、MIT 许可证及 Windows / Ubuntu / macOS CI。依赖读取 requirements.txt，版本读取现有 filemind.__version__，保留 0.1.0。GUI 安装入口继续走本机锁屏。

## 整合时额外修正

- 保留 `filemind/models/` 兼容导出，新增字段放进现有数据模型，而非恢复旧的 models.py。
- 编辑先构建候选计划，校验成功才提交；相对子目录不得通过去除开头斜杠来接受绝对路径。新名称在本地再次检查扩展名。
- Qt 编辑角色返回现有值，双击修改不会得到空白编辑框；保留请求名称与去重后名称的区别。
- 执行列使用单独代理，点击勾选框或单元格只切换一次，避免默认勾选处理与 clicked 回调重复翻转。
- 预览编辑同步主工作区、目录树与统计；关闭预览会解除模型信号连接。已排除状态优先显示，不再被原冲突状态盖住。
- 历史页面展示跳过原因，全部跳过时不提供无效撤销操作。
- 预览美化：执行列固定放在最左侧；绿色校验、灰色排除、橙色冲突标签；编辑框、详情卡片、未执行提示和文件夹按钮统一样式。主工作区同样显示状态标签，长目录不会撑开历史页面。
- 字体适配保留“已安装字体直接使用”的优化；wheel 包额外包含 orbit.qss、SVG、品牌图标和 models 包。
- 保留原有执行前确认、路径校验、源文件状态检查、无覆盖发布与撤销校验。没有读取或迁移真实密钥配置，没有增加文件正文或递归扫描能力。

## 主要文件

| 模块 | 文件 |
| --- | --- |
| 数据与核心 | filemind/models/models.py、core/planner.py、core/plan_editor.py、core/executor.py |
| 编辑预览与联动 | ui/dialogs/plan_preview.py、ui/widgets/file_table.py、plan_tree.py、organization_workspace.py、ui/pages/organize_page.py、history_page.py、ui/main_window.py |
| 平台兼容 | storage/paths.py、settings.py、chat_history.py、local_lock.py、workspace.py、ui/dialogs/local_lock.py、ui/styles/theme.py、conversion/office.py |
| 工程配置 | pyproject.toml、LICENSE、.github/workflows/ci.yml、README.md |
| 测试 | tests/test_plan_editor.py、test_paths.py、test_branch_integration.py；调整 test_executor.py、test_local_lock.py、test_lock_controller.py、test_organization_workspace.py 与 conftest.py |

## 验证记录

- 修改前基线：`py -3.13 -m pytest -q`，192 passed、24 subtests passed，219.83 秒。
- 核心与存储阶段：37 passed、12 subtests passed。
- 初次 UI 回归出现一次后台等待失败，单独重跑可复现。真实 Qt 事件循环执行同一任务约 0.078 秒完成；将测试中的轮询等待改为事件循环，保留原 5 秒上限和原业务断言。对应回归通过。
- 预览与整合阶段：35 passed。阶段中修正了混合冲突测试夹具重新分类导致目标改变的问题，以及美化按钮使用了不存在的图标名称的问题；原业务断言保留。
- `py -3.13 -m compileall -q main.py filemind tests tools`、`py -3.13 -m pip check` 及 Git 空白检查通过；Git 仅提示现有 LF/CRLF 规范化信息。
- 最终 wheel 构建成功：`py -3.13 -m pip wheel . --no-deps --no-build-isolation --wheel-dir .artifacts/branch-integration/final-dist`。确认包含 QSS、头像品牌素材、自有弹层、models 包和编辑器，无 .env 或 local_api_keys 文件。从解包后的安装目录导入、应用主题、加载品牌图标和入口导入均通过。
- Windows Qt 实际启动检查 1024×700、1280×850：预览编辑、勾选、主工作区同步、历史展示及 Orbit 导航；两种尺寸预览的横向滚动最大值均为 0。另验证真实编辑框 Enter 提交、拒绝扩展名变更。
- 使用生成的临时目录实际完成 3 项移动、2 项跳过，并安全撤销 3 项成功移动；原冲突目标内容保留。截图位于 `.artifacts/branch-integration/ui/`。
- 完整回归：`py -3.13 -m pytest -q`，212 passed、24 subtests passed，415.17 秒。相比本次基线新增 20 项测试；未删除或跳过原用例。

所有测试文件均为临时生成数据；没有对用户真实目录执行整理或撤销，没有发起真实模型请求。没有删除现有测试；原“目标冲突抛出整批异常”用例更新为“明确跳过且不覆盖”，并新增操作日志断言以对应本次业务变化。

## 依赖与许可证

运行依赖及其版本不变，没有新增 UI 框架。新增构建后端要求 setuptools >=77，MIT 许可证；本机验证版本为 84.0.0。项目 LICENSE 保留队友提供的 MIT 版权与许可声明。未引入其他 GitHub UI 项目代码。

## 限制

- 本次本机验证目标为 Windows + Python 3.13。CI 已配置三平台，本次没有推送或取得新的远端 CI 结果，不能宣称已完成三平台验收。
- macOS 采用 Application Support 新路径，历史旧路径不自动迁移；Linux 按 XDG 规则处理。没有读取、复制或重写任何实际本机配置。
- 部分成功不会回滚已经成功的其他文件，结果逐项记录，可对成功项使用安全撤销。
- 顶层扫描、AI 元数据隐私范围、API 兼容边界和转换后端能力保持现有设计；没有合并不存在于来源仓库中的正文提取或递归扫描开发分支。
