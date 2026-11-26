# DeskCal + Anki（fork 开发版）

基于 [HANSEIDON/DeskCal 1.3.2](https://github.com/HANSEIDON/DeskCal/commit/e6c62fcfae19b317b66a48ba8bb89cca2da216b9)，fork：[Z3O1/DeskCal](https://github.com/Z3O1/DeskCal)。

## 行为

- 原版 Tk/Win32 窗口、壁纸磨砂、Calendar、Timetable、尺寸及原齿轮设置保留。
- 顶部新增 `Calendar | Anki | Timetable`。Anki 页始终可以进入；未连接时在页内显示 **“未连接到 Anki”** 和“重新连接”按钮，不启动 Anki、不弹对话框。只有已运行、已打开档案且 AnkiConnect 可用时才显示卡片。
- 掉线后留在 Anki 页并清除旧卡片，禁用评分。自己打开/重启 Anki 后，点“重新连接”或再点 Anki 页签即可；重连会重新读取本地端口和密钥，不会在后台自动启动复习。
- Anki 页占满正文，显示原模板 HTML/CSS/JS 和媒体，底部翻面/评分，间隔取自原生排程。背景只在运行时透明，不修改存储的模板。
- 默认牌组：`英语单词::大学四级英语单词`。不直接打开任何 `collection.anki2`，不复制牌库；评分由 AnkiConnect 调用当前 Anki 的原生排程。
- 原有 `anki_dark_card/dark.css` 原文只读复用，Zoom（1923741581）当前正/反面缩放配置只读复用。**不保证任意第三方插件都能自动继承**；AnkiConnect 本身不返回通用的 `card_will_show` 最终结果。
- 浏览器里的空格/Enter 翻面，答案面空格评“良好”；1–4 对应当前提供的评分，R 重播，Ctrl+Z 调用 Anki 撤销。Calendar 中原有撤销逻辑不变。

## 依赖与连接

- Windows 10/11 x64、带 Tkinter 的 Python 3.10+、微软 WebView2 Runtime。
- 已运行的 Anki；接口使用官方 AnkiConnect 26.11.22.0 的 `/api/v1`（已在 Anki 26.9.2 临时档案验证）。这不是旧的 DeskCal Anki 插件。
- 不向卡片 JavaScript 传递 API 密钥、排程 token 或媒体文件系统路径。
- 默认从同一 Windows 用户的 `%APPDATA%/Anki2/addons21/2055492159` **只读**获取本地 AnkiConnect 的端口与密钥，不修改插件文件。远程地址不会自动使用本地密钥。
- 如需手动配置，在 DeskCal 数据目录放 `anki-connect.json`（源码版为旁边的 `data/`，可通过 `DESKCAL_DIR` 指定）：

```json
{
  "endpoint": "http://127.0.0.1:8766/api/v1",
  "api_key": "你的密钥",
  "deck": "英语单词::大学四级英语单词"
}
```

以上以接口已配置为 `8766` 为例。通常不必创建此文件，程序会自动读取 AnkiConnect 的实际端口；手写 `endpoint` 会覆盖自动发现。

可选项 `addons_dir` 指定插件目录，`web_assets` 指定当前 Anki 的 `_aqt/data/web` 目录。密钥/个人配置不得提交或打包。

如果 Anki 已开却仍未连接，请检查端口是否被其他网页服务占用；`HTTPError 404` 不等于 Anki 已关闭。调整 AnkiConnect 端口后需自行重启 Anki，再点“重新连接”。不要擅自关闭占用端口的其他服务。

## 构建

微软 SDK 版本为 `Microsoft.Web.WebView2 1.0.3856.49`。准备包含以下文件的目录：

- `Microsoft.Web.WebView2.Core.dll`（SDK 的 .NET Framework 版本）
- `WebView2Loader.dll`（x64）
- `WEBVIEW2-LICENSE.txt`（SDK 原许可证）

```text
python tools/build_anki_host.py --sdk SDK目录
python tools/build.py --anki-host build/anki-host
```

原版 Nuitka 构建流程保留，额外携带透明宿主、SDK DLL/许可证和 HTML 外壳；卡片资源使用本机已安装的 Anki，不另复制 Anki 的网页资源。

用户已确认：保留原版正常首次运行时默认开启开机启动，只检查 `Z3O1/DeskCal` 的发布；旧上游的更新缓存会失效，不会拿原版安装包覆盖融合版。当前开发过程没有写入 Windows 启动项。

**开发状态：最终 Windows 本地安装验收尚未完成。** 保留原版数据目录和单实例机制；若原版 DeskCal 正在运行，需由你自行退出后再运行 fork，否则启动器可能召回原版窗口。不会自动关闭原版或 Anki。

### 源码预览包（不是独立安装版）

```text
python tools/package_anki_preview.py --host build/anki-host
```

生成 `dist/DeskCal-Anki-preview-source.zip`，携带原版字体和已编译的 WebView2 宿主，不携带 Python、个人配置或牌库。包内含文件 SHA-256 清单，旁边生成 ZIP 的校验文件。

如需自行预览，应先解压到固定的 **Windows 本地磁盘目录**，不要从 WSL UNC 路径运行（Windows 曾拒绝从该路径加载随附字体）。先自行启动已加载 AnkiConnect 的 Anki，再运行 `DeskCal.bat`。首次正常启动会按已确认策略设置开机启动；这一步不是开发测试，当前没有代你执行。

## 不占用桌面的测试

禁止在用户当前 Windows 桌面跑 GUI/截图/键鼠测试。使用 Linux 的独立环境：

```text
python tools/test_anki_headless.py --ankiconnect 官方AnkiConnect源码目录
# 可选：--dark-card 现有anki_dark_card源码目录
```

测试进程强制 `QT_QPA_PLATFORM=offscreen`，移除 DISPLAY/Wayland，使用临时档案、随机端口和测试密钥。

已覆盖：原导航方法与控制器的纯逻辑、离线页/明确重试/掉线清卡、真实 HTTP 翻面/评分、revlog 只增加一次、过期评分拒绝、dark-card 最终 HTML 逐字对照、JS/媒体、正背 sessionStorage、透明 CSS、缩放与重连防护、fork 更新 URL/旧缓存隔离和默认开机启动代码。`--dark-card` 可对照现有插件；未指定时使用合成 CSS 夹具，不依赖个人文件。

**未由无界面测试证明：** 最终 Windows 原生合成、焦点、字体加载和安装包显示。此前可见桌面测试已停止；原版回归 326/329，3 项字体失败的日志显示 Windows 未能从 WSL UNC 路径加载原版 Noto 字体。字体代码和资源未改，需另行授权的隔离 Windows 环境复验，不能用 headless 结果冒充。
