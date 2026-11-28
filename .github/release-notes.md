## 下载 / Downloads

- **`DeskCal-1.4.0-Setup.exe`**：推荐，当前用户安装，无需管理员权限；创建独立的 “DeskCal - Anki” 开始菜单入口和卸载项。
- **`DeskCal-1.4.0-windows-x64.zip`**：便携版，解压后运行 `DeskCal/DeskCal.exe`。
- 每个文件附带 SHA-256 校验文件。

无需另外安装 Python、Anki 或 AnkiConnect；仍需 **Microsoft WebView2 Runtime**（Windows 11 通常已具备）。

## 本版功能

- 保留原版日历、课表和桌面磨砂界面。
- 内置官方 Anki 26.9.2 内核，使用 DeskCal 独立牌库。
- 在齿轮设置中登录 AnkiWeb、手动同步牌库和媒体、选择学习牌组及导入/导出 `.apkg`。
- 全量同步覆盖方向必须明确选择并再次确认；密码不保存，可选择用户级 DPAPI 加密记住登录令牌。

## 安装前请注意

- 请自行退出旧 DeskCal；安装器不会强制关闭、自动启动或重启 DeskCal / Anki。
- 安装目录为当前用户的 `AppData\Local\Programs\DeskCal-Anki`。原日历/课表、内置牌库、媒体和加密登录文件保留，卸载也不删除个人数据目录。
- 安装器不会直接打开或改动原 Anki 的个人牌库。AnkiWeb 同步作用于整个账号牌库，不限于所选学习牌组，云端变化会影响其他客户端后续同步。
- 程序首次正常运行仍默认开启开机启动，已有用户的偏好会保留；安装完成后不会自动运行程序。
- 这是未签名的社区构建，可能出现 Windows SmartScreen 提示。

## 已知边界

- 按用户要求只执行了编译和文件完整性检查，**未运行应用、GUI、登录或同步测试**。
- 深浅色卡面配色适配仍待改善；不保证外部 Anki 桌面插件兼容或继承。
- 当前没有完整卡片编辑器、自建同步服务器配置或插件管理。

## 来源与许可

Windows 程序来自成功的 [GitHub Actions 编译](https://github.com/Z3O1/DeskCal/actions/runs/46142279263)，原始运行时代码提交为 `525f7f5`。Setup 复用该编译结果，逐项确认运行时代码一致后补充本版本的安装配方、文档及独立打包来源信息，没有重新编译或替换运行时代码。

原 DeskCal MIT 声明保留；内置集成与组合发行遵循 **AGPL-3.0-or-later**。安装包和 ZIP 携带许可证、对应运行时/上游源码及安装构建脚本，本 Release 的源码标签也包含完整打包配方。不是 Anki 官方发行版。
