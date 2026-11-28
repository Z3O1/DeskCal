# DeskCal · 内置 Anki

在原版 [DeskCal 1.3.2](https://github.com/HANSEIDON/DeskCal) 的 Calendar / Timetable 之间加入 Anki 页。当前 fork 使用 **官方 `anki==26.9.2` 内核**，不是自行实现排程算法，也不再连接外部 Anki 或 AnkiConnect。

## 安装版

在 [融合版 Releases](https://github.com/Z3O1/DeskCal/releases) 下载 **DeskCal-1.4.0-Setup.exe**（当前用户安装，无需管理员权限）或独立 ZIP。Setup 使用融合版自己的 AppID 和 `DeskCal-Anki` 目录，不覆盖原版安装注册。

请先自行退出旧 DeskCal。安装器不会自动关闭、启动或重启 DeskCal / Anki；安装后从原 **DeskCal - Anki** 开始菜单入口打开。已有日历/课表、内置牌库、媒体、登录文件和 `data` junction 保留，卸载也不删除个人数据。

安装版与独立 ZIP 不需要 Python、Anki 或 AnkiConnect，但仍需系统 **WebView2 Runtime**。程序首次正常启动按原有策略默认启用开机启动，已有偏好保留；安装过程不提前更改这一偏好。

## 使用

1. 打开原齿轮 **设置 → Anki · 账户与牌组**；首次使用会创建 DeskCal 自己的空牌库，不需要先进入 Anki 页。
2. 在设置中填写 AnkiWeb 邮箱和密码，点 **登录 AnkiWeb**。登录本身不上传或下载数据；点 **立即同步牌库和媒体** 才开始同步。
3. 在同一区域的 **学习牌组** 下拉框选择要复习的牌组，选择会记住；卡片页不再显示牌组菜单。
4. 也可以在设置中 **导入牌组 (.apkg)**。从原 Anki 手动导出带学习进度和媒体的 `.apkg` 后导入即可；DeskCal 不直接打开你的原牌库。
5. 打开 Anki 页，底部翻面、评分。空格 / Enter 翻面，答案面空格评“良好”，1–4 评分，R 重播，Ctrl+Z 撤销。输入答案卡片使用原生答案比较接口。
6. 设置中的 **导出全部牌组和学习进度** 导出带媒体和进度的 `.apkg`。为避免意外覆盖，目标文件名必须尚不存在。

关闭外部 Anki 不影响内置模式；DeskCal 也不会替你启动、关闭、重启或修改外部 Anki。原 Calendar / Timetable、壁纸磨砂、尺寸和齿轮设置保持原样。

## AnkiWeb 同步与登录安全

- 复用官方内核的登录、增量/全量牌库同步和媒体同步；不使用 AnkiConnect 或自己实现同步协议。只在你点击按钮时联网，不在启动、退出或复习后自动同步。
- **同步对象是 AnkiWeb 账号中的整个牌库，不是“学习牌组”下拉框所选的一个牌组。** 不直接操作原 Anki 的本地数据库，但云端变更会影响手机和其他客户端的后续同步。
- 首次连接或结构冲突可能要求全量同步。设置中明确区分 **从 AnkiWeb 下载（覆盖 DeskCal）** 和 **上传 DeskCal（覆盖 AnkiWeb）**，只提供服务端允许的方向；点击后还需再次确认，默认取消。全量不是合并。
- 上传覆盖可能丢失云端独有的卡片/进度，下载覆盖可能丢失 DeskCal 独有的数据。操作前备份本地牌库，但不能代你备份其他客户端的云端独有内容；必要时先在原客户端完成同步和导出。
- 牌库和媒体分别显示进度，可取消。取消不会回滚已经完成的同步变更；媒体失败会明确提示，不把“牌库已同步”说成“全部完成”。全量覆盖请求不自动重试。
- 密码只用于本次登录请求，不存入设置、日志或卡片 WebView。勾选 **记住登录** 时，用 Windows 用户级 DPAPI 加密保存会话令牌；不勾选则只保留在进程内，没有明文文件兜底。不要把令牌文件当作跨机器登录凭据复制。
- 退出登录清除本机令牌，不删除牌库，也不撤销已完成的云端变更。更换账号会提示，并要求重新确认全量同步方向，避免复用另一账号的同步状态。
- 所有账户/牌库动作仍在专用线程；仅官方客户端同样使用的 Rust 后端进度/取消 RPC 在监控线程调用，不跨线程操作 Python 牌库对象。同步期间不接收复习评分。

一手实现依据：[固定版本官方同步流程](https://github.com/ankitects/anki/blob/26.09.2/qt/aqt/sync.py)、[媒体监控](https://github.com/ankitects/anki/blob/26.09.2/qt/aqt/mediasync.py)、[Anki 同步说明](https://docs.ankiweb.net/syncing.html)、[Microsoft DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)。

## 数据隔离

内置数据固定在 DeskCal 数据目录下，不扫描或打开 `%APPDATA%/Anki2`：

```text
DeskCal 数据目录/
  anki/
    collection.anki2
    collection.media/
    collection.media.db2
    settings.json
    ankiweb-auth.bin        # 可选：Windows 用户级 DPAPI 加密令牌，不含密码
    backups/
  anki-webview-profile/
```

源码版的数据目录为旁边的 `data/`；独立 exe 为 `%LOCALAPPDATA%/DeskCal`；`DESKCAL_DIR` 可以指定整个 DeskCal 数据目录，但不能单独指定外部 collection 路径。

内核操作在一个专用线程内串行执行；评分使用官方 `get_queued_cards` / `build_answer` / `answer_card`，不直接写 SQL。会话和状态标记阻止重复/过期评分，评分失败不会自动重试写入。导入前生成内核备份；自动备份不包含媒体，需要完整备份时使用导出功能。原版 Calendar 的备份功能仍只负责原版数据，不代替 Anki 导出。

## 卡面与兼容边界

- 使用内核渲染的原模板 HTML/CSS，沿用透明 WebView2 卡片宿主和同版本官方 reviewer.js；资源随 DeskCal 携带，不再从外部 Anki 取文件。
- 支持普通卡片、挖空、模板 JavaScript、输入答案、媒体及原生排程。HTML5 音视频支持取决于 WebView2 编解码器；TTS 使用系统浏览器语音，声音和桌面 Anki 的 mpv/TTS 可能不同。
- 不加载外部桌面插件，也不自动读取 dark-card / Zoom 的配置。需要的样式应随自己的模板导入。
- 已接入设置内的 AnkiWeb 登录、手动牌库/媒体同步；当前不提供卡片编辑器、桌面插件管理或自建同步服务器配置。
- 自定义排程 JavaScript 暂不支持，检测到时阻止复习，而不是悄悄按另一套规则评分。
- 导入/导出当前只接受 `.apkg`；不接受 `.anki2`、`.colpkg` 原地替换整个牌库。只导入你信任的模板，模板 JavaScript 会在卡片 WebView 内运行。
- 卡片 JavaScript 无法取得牌库路径、排程 token 或任意文件访问接口；媒体由原生宿主从内置媒体目录提供，不新增 HTTP 监听器。

## 源码预览包

现有 `dist/DeskCal-Anki-embedded-source.zip` 面向 **Windows x64 + Python 3.14（含 Tk）+ WebView2 Runtime**，随包携带：

- 官方 Windows Anki 内核及依赖，不用另外安装 Anki / AnkiConnect；
- 官方同版本 reviewer 静态资源；
- 已编译的 WebView2 宿主及 SDK DLL；
- 原版字体、源码、许可证、上游 Anki 源码归档及 SHA-256 清单。

源码预览包**不是免 Python 的独立安装版**。解压到固定的 Windows 本地目录，运行 `DeskCal.bat`；不要从 WSL UNC 路径运行（旧记录中 Windows 无法从该路径加载部分字体）。不要覆盖原版的数据目录；若旧 DeskCal 正在运行，由你自行退出后再运行，以免单实例机制召回旧窗口。

其他 Python 版本可以在对应环境安装 `python -m pip install -r requirements-anki.txt`，或重新生成匹配的 vendor 目录。启动器优先使用已随包附带依赖的 Python 3.14；不会自动联网安装依赖。

首次正常启动仍按原有已确认策略默认启用开机启动；更新只跟随 `Z3O1/DeskCal`，不会安装旧上游版本。

## GitHub Actions 构建独立版

在仓库的 **Actions → Build Windows (embedded Anki) → Run workflow** 手动触发：

```text
gh workflow run build-windows.yml --repo Z3O1/DeskCal --ref main
```

云端使用 Windows 2022 / Python 3.12 / MSVC，下载固定版本 WebView2 SDK，编译宿主并用固定版本 Nuitka 打包。成功后从该次运行的 **Artifacts → DeskCal-Windows-x64-…** 下载 ZIP 和 SHA-256；解压得到 `DeskCal/DeskCal.exe`，无需另外安装 Python 或 Anki，仍需系统 WebView2 Runtime。

产物同时携带内核扩展、资源、许可证、对应源码和构建信息。仅编译与文件检查，不启动 exe、不运行任何测试、登录或真实同步，也不会自动发布 Release 或覆盖本机版本。

## Setup 构建与发布

已有成功的 Windows ZIP 时，可在 **Actions → Build Setup (existing Windows artifact)** 输入对应运行 ID，或：

```text
gh workflow run build-setup.yml --repo Z3O1/DeskCal --ref main -f source_run_id=46142279263
```

Setup workflow 只有读取权限，不自动发布：它核对原 ZIP 的 SHA-256、构建来源及当前运行时代码，复用原二进制，在独立 Windows runner 上用预装 Inno Setup 编译安装器。若运行时代码已变更，必须先重新执行 Windows 编译。Setup 和重新打包的 ZIP 都携带最新安装源码、许可证和独立来源信息。

安装器文件名为 `DeskCal-<版本>-Setup.exe`，旁边有 `.sha256`，与融合版更新器匹配。确认构建成功及产物后，只有在用户明确要求发布时才创建新的 `v<版本>` Release，不覆盖已存在的 tag/Release。

## 本地构建说明

Windows 编译环境使用 Python 3.12（与 Actions 相同）。准备包含 `Microsoft.Web.WebView2.Core.dll`、x64 `WebView2Loader.dll`、`WEBVIEW2-LICENSE.txt` 的 SDK 目录（SDK 1.0.3856.49）。Windows 下运行：

```text
python tools/build_anki_host.py --sdk SDK目录
python tools/build.py --anki-host build/anki-host
```

独立 Nuitka 构建会在隔离环境安装固定版本内核，随包携带 Python、内核、本机扩展和卡片资源，不依赖外部 Anki。`prepare_anki_assets.py` 只下载/提取 aqt wheel 的静态资源，不安装 Qt 或启动 Anki GUI。

仅生成源码预览包（可在 Linux 下载和组装，不执行 Windows 文件）：

```text
python tools/prepare_anki_assets.py
python tools/prepare_anki_vendor.py --python-version 3.14
python tools/package_anki_preview.py --host build/anki-host
```

`anki_webview/assets/`、`anki_vendor/`、`build/`、`dist/` 为可重建产物，不提交个人数据。

## 许可与验证状态

原版 DeskCal 的 MIT 声明保留在 `LICENSE`。内置 Anki 集成及组合发行遵循 AGPL-3.0-or-later，完整许可见 `COPYING`、`LICENSING.md` 和 `THIRD_PARTY_NOTICES.md`。分发时请保留源码、构建脚本和依赖声明，并核对相应依赖的许可要求。

**按用户要求，不运行应用、单元/集成测试、Windows GUI、截图或键鼠自动化。** 没有实际登录任何 AnkiWeb 账号、调用 DPAPI 或执行联网同步。GitHub Actions 只执行云端编译、打包和文件完整性检查；本机不启动 Windows 编译器。编译成功不代表运行验收通过，历史 AnkiConnect 测试也不能证明当前内置实现或同步正确。安装/覆盖本机版本需要另行明确授权。
