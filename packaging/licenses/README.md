# 发布依赖许可原文

- `GPL-3.0.txt`：来自 https://www.gnu.org/licenses/gpl-3.0.txt ，供当前附带的 FFmpeg GPLv3 许可和 Qt 许可引用。
- `LGPL-3.0.txt`：来自 https://www.gnu.org/licenses/lgpl-3.0.txt ，对应 Qt/PySide6 元数据中声明的 LGPL 选项。

构建准备阶段另行复制实际安装的 Python 依赖许可证，并记录其名称、版本和声明。FFmpeg 的许可短文从打包后的实际二进制 `-L` 输出提取；不是把 `imageio-ffmpeg` Python 包本身的 BSD 许可当作 FFmpeg 二进制许可。

保留许可文本不能替代各组件的其他分发要求。尤其是当前 GPLv3 FFmpeg，应按 [FFmpeg 官方许可说明](https://ffmpeg.org/legal.html) 提供对应源码或合规来源；Qt/PySide6 按 [Qt for Python 的许可说明](https://doc.qt.io/qtforpython-6/licenses.html) 处理。FileMind 自有源码的 MIT 许可不重新授权这些组件。
