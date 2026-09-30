<img width="2560" height="1380" alt="image" src="https://github.com/user-attachments/assets/253d6a99-85d5-4875-b007-b6f840ce569d" /># CourseBeacon

> 使用 Python 与 Playwright CLI 汇总超星未完成作业的 Windows 本地工具。

CourseBeacon v2 在本机 Chrome 中打开 `http://127.0.0.1:17890`，连接用户现有 Chrome 会话，读取课程中的未完成作业，并显示原网页风格的作业行及直达链接。

## 目录

- [功能特性](#功能特性)
- [技术栈及其作用](#技术栈及其作用)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [刷新与失败处理](#刷新与失败处理)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [实现步骤](#实现步骤)
- [源码运行与打包](#源码运行与打包)
- [本地接口](#本地接口)
- [数据存储](#数据存储)
- [测试](#测试)
- [已知限制与常见问题](#已知限制与常见问题)
- [许可证与资源说明](#许可证与资源说明)

## 功能特性

- **启动检查一次**：首次启动触发一轮检查，此后只在点击按钮时检查，不进行定时扫描。
- **标题下方按钮**：“检查作业”按钮位于 CourseBeacon 标题下方居中，扫描期间禁用重复触发。
- **复用本机 Chrome**：通过 `playwright-cli attach --cdp=chrome` 连接日常 Chrome，复用其现有登录状态，不复制或替换用户资料目录。
- **独立扫描标签**：仅操作程序新建的扫描标签，以 Chrome target ID 定位，避免导航用户原有标签页。
- **未完成作业汇总**：排除明确标注“课程已结束”的课程，读取“作业 → 未完成”的所有受支持分页。
- **直达链接与原样时间**：使用原网页链接和剩余时间文本，保留作业行的图标、字号和状态颜色。
- **有限重试与缓存保留**：临时错误最多重试一次；登录或浏览器失效立即停止本轮，不逐门重复失败。
- **安全退出**：退出仅关闭本程序的扫描标签并断开调试连接，不关闭用户 Chrome。
- **重复启动保护**：同一数据目录限制一个新版实例；再次启动打开已有服务页面。

程序不会填写或提交作业。

## 技术栈及其作用

以下为本项目使用的构建版本，并非声明其他版本均已验证。

| 技术 / 模块 | 版本或形式 | 作用 |
| --- | --- | --- |
| Python | 3.13.1 x64 | 启动入口、配置、扫描任务调度、结果整理 |
| `http.server` | 标准库 | 通过 `ThreadingHTTPServer` 提供本地静态页面和 JSON API |
| `threading` | 标准库 | 后台扫描线程、手动触发事件和状态锁 |
| `subprocess` | 标准库 | 按参数列表调用 Node 与 Playwright CLI |
| Node.js | 24.15.0 | 执行 CLI 及其依赖 |
| `@playwright/cli` | 0.1.13 | 连接现有 Chrome、执行页面和 iframe 提取脚本 |
| Chrome / CDP | 本机 Chrome；开发机器为 154 | 提供已登录的真实浏览器会话及标签页标识 |
| SQLite / `sqlite3` | Python 标准库 | 持久化最近一次汇总快照 |
| HTML / CSS / JavaScript | 原生前端 | 展示列表、按钮与设置，通过 Fetch API 读取本地状态 |
| `msvcrt` | Windows 标准库接口 | 单实例文件锁，防止多个新版实例争用同一数据目录 |
| `RotatingFileHandler` | Python 标准库 | 限制日志大小，避免反复失败产生无限增长日志 |
| PyInstaller | 6.16.0 | 打包 Python、Node、CLI、提取脚本和页面资源 |
| `unittest` | 标准库 | 回归验证刷新调度、失败处理、缓存和本地接口 |

应用没有使用 FastAPI、Vue、Element Plus、Axios 或 Python 版 Playwright。当前技术栈以实际源码为准。

## 环境要求

### 运行 exe

- Windows 10/11 x64；构建环境为 Windows 11 x64。
- 安装支持 `chrome://inspect/#remote-debugging` 的 Google Chrome。
- Chrome 中已允许远程调试，并在首次连接时允许连接请求。
- 能正常访问超星，且本机 Chrome 中的账号可访问目标课程。

exe 内置 Python、Node 和 Playwright CLI；不包含 Chrome。

### 开发环境

Python 3.13 x64、Node.js、npm、Google Chrome，以及 `requirements-build.txt` 中的构建依赖。

## 快速开始

1. 先退出旧版 CourseBeacon，避免旧版继续按 60 秒间隔扫描或占用端口。
2. 在日常使用的 Chrome 中打开 `chrome://inspect/#remote-debugging`，允许对此浏览器实例进行远程调试。
3. 双击新版 `CourseBeacon.exe`。程序使用普通 Chrome 启动方式打开本地页面，不指定独立 `--user-data-dir`。
4. 如 Chrome 显示连接确认，请允许。程序新建扫描标签并进行一次检查。
5. 如果超星尚未登录，在扫描标签中登录；本次启动检查会等待登录后继续。
6. 后续点击标题下方居中的“检查作业”获取新结果。扫描完成后不会自动再次读取超星。
7. 点击作业行可在新标签中打开作业；悬停可查看课程名称。
8. 通过“设置 → 退出 CourseBeacon”退出。用户 Chrome 和原有标签页保持打开。

如果连接未成功，页面会显示调试设置说明。完成设置后点击“检查作业”即可重试，无需反复重启程序。

### 与旧版持久化模式的区别

旧版 `CourseBeacon-persistent.exe` 使用 `open --persistent --profile=...`，持久化的是 CourseBeacon 的独立浏览器资料。

v2 改为 `attach --cdp=chrome`，直接连接用户现有 Chrome。它不导入旧版 Cookie、不复制日常 Chrome 资料，也不会修改用户的书签或浏览器设置。用户需自行允许 Chrome 的调试连接。调试开关并不意味着登录永久有效，超星会话过期时仍需登录。

## 刷新与失败处理

### 触发规则

- 启动时自动检查一次。
- 后续只能由“检查作业”按钮触发。
- 扫描期间的重复触发不排队，不额外生成一轮任务。
- 失败后不按定时器重试，保留错误提示供用户处理后手动重试。
- 前端约每 1.5 秒读取一次本地状态，这只访问 `127.0.0.1`，不会触发超星扫描。

### 错误处理规则

| 情况 | 处理方式 |
| --- | --- |
| 临时导航或列表读取失败 | 从课程入口重新读取一次，仍失败则记录课程错误 |
| 超星登录失效 | 立即停止本轮，提示登录，未检查课程不冒充成功 |
| 浏览器连接或扫描标签已关闭 | 停止本轮，下一次手动检查重新连接 |
| 人脸采集或访问验证 | 不重复尝试绕过验证，报告该课程的要求 |
| 连续 3 门课程发生一般读取错误 | 提前停止本轮，提示检查网络和剩余课程未检查 |
| 单门课程读取失败且存在旧数据 | 保留旧条目并标记待核验 |
| 已成功读取且确认没有未完成作业 | 移除该课程的旧条目 |

剩余时间按**最近一次检查时**超星提供的原文显示。程序不按秒倒计时；需要获取最新时间时，点击“检查作业”。

## 配置说明

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-p` / `--port` | 配置文件值，否则 `17890` | 本地端口，范围 `1024–65535` |
| `--data-dir` | `%LOCALAPPDATA%\CourseBeacon` | 缓存、日志和应用配置目录；不是 Chrome 资料目录 |

```powershell
.\CourseBeacon.exe --port 9000
```

```powershell
.\CourseBeacon.exe --data-dir ".\local-data"
```

v2 已移除 `--interval`、`--profile` 和旧的开发附加模式。内部 CLI 会话名为每次运行生成的唯一值，避免不同进程争用固定会话。

页面设置保存的端口在下次启动生效。端口优先级为“命令行 → 配置文件 → 默认值”。`config.json` 示例：

```json
{
  "port": 17890
}
```

## 项目结构

```text
CourseBeacon/
├─ app.py                    # 本地服务、手动调度、错误处理、单实例与缓存
├─ bridge.py                 # Chrome 启动、CLI attach、扫描标签定位及 detach
├─ build.py                  # 准备运行时和 exe 打包
├─ requirements-build.txt    # PyInstaller 构建依赖
├─ test_app.py               # 单元与回归测试
├─ README.md
├─ scripts/
│  ├─ courses.js             # 从 iframe 中读取根课程列表
│  └─ assignments.js         # 作业页识别、筛选、分页及访问状态检测
├─ static/
│  ├─ index.html             # 标题、居中检查按钮和列表
│  ├─ style.css              # 页面及作业行样式
│  ├─ app.js                 # 本地状态轮询和手动操作
│  ├─ icons-act.png
│  └─ endTime.png
├─ build-work/               # 构建时生成
└─ dist/                     # 构建时生成 CourseBeacon.exe
```

## 实现步骤

### 1. 初始化配置并限制重复启动

解析端口和数据目录，通过 `msvcrt.locking` 锁定 `instance.lock`。同一目录已有新版实例时，读取它记录的端口并打开现有页面。每次运行采用唯一 CLI 会话名。

### 2. 启动本地网页服务

使用 `ThreadingHTTPServer` 绑定 `127.0.0.1`，提供静态资源和 JSON API。后台线程与 HTTP 服务分离，页面可在扫描期间展示进度或请求退出。

### 3. 使用日常 Chrome 打开网页并连接

通过本机 Chrome 可执行文件正常打开本地 URL，不添加资料目录参数。后台调用：

```text
playwright-cli -s=<本次唯一会话名> attach --cdp=chrome --raw
```

连接后通过 CLI 新建扫描标签，使用 CDP 的 `Target.getTargetInfo` 记录该标签的 target ID。后续脚本定位到该标签才执行，避免误操作当前选中的个人标签页。

### 4. 等待登录并发现课程

导航到超星个人空间，遍历页面及 iframe，查找 `#courseList`。登录等待最多 10 分钟；非登录状态的列表加载等待约 45 秒，避免无限循环。

课程提取使用 `#courseList > li.course`，排除 `.not-open-tip` 明确包含“课程已结束”的卡片。发现课程文件夹时报告当前兼容限制。

### 5. 检查未完成作业

逐门进入课程并等待“作业”入口。查找页面或 iframe 中的 `.task-list #status`，点击 `input[name="group-radio"][data="1"]` 后，等待筛选值确认变为 `1`。

等待页面加载期间同时检查登录跳转、人脸采集及访问验证提示，避免在已知无法继续的页面等到完整超时。

### 6. 分页提取并校验链接

从 `.bottomList > ul > li` 读取作业名称、状态、直达 URL、时间原文、图标类别和附加标签。有下一页时，等待列表内容变化后继续读取，按 URL 去重，设置 200 页保护上限。

Python 补充所属课程、条目 ID 和读取时间，校验链接属于超星域名。

### 7. 更新结果与保存快照

每门课程成功读取后，用新结果替换该课程的旧条目。如果确认该课程没有未完成作业，其旧条目会被移除。

单门课程失败时，保留该课程的旧条目并标记 `stale`，同时记录错误；其他课程继续扫描。一轮结束后将汇总状态保存为 SQLite 中的 JSON 快照。

### 8. 渲染页面和作业链接

前端 `static/app.js` 轮询 `/api/state`，使用 DOM API 和 `textContent` 构建作业行。作业标题、状态及时间分别放入对应样式区域，链接以新标签页打开。

样式采用原网页的标题字号、灰色状态、橙色剩余时间和作业图标，去除参考截图中用于标注的红框。课程名称放在悬停提示中。

### 8. 等待手动触发

扫描线程通过无超时时间的 `Event.wait()` 等待。只有启动事件、用户检查按钮或退出事件会唤醒线程。不存在每隔 60 秒自动发起扫描的逻辑。

### 9. 退出时保留用户浏览器

只关闭程序记录的扫描 target，然后执行 `playwright-cli detach`。不调用关闭整个浏览器的命令，不终止 Chrome 进程。

## 源码运行与打包

在源码根目录使用 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
npm install -g @playwright/cli@0.1.13
.\.venv\Scripts\python.exe build.py --prepare
```

设置源码运行时路径：

```powershell
$env:COURSEBEACON_NODE = "$PWD\build-work\runtime\node.exe"
$env:COURSEBEACON_CLI = "$PWD\build-work\runtime\cli\playwright-cli.js"
.\.venv\Scripts\python.exe app.py --port 17890
```

生成 exe：

```powershell
.\.venv\Scripts\python.exe build.py
```

构建结果为 `dist/CourseBeacon.exe`。构建脚本复制已安装的 Node、CLI 及其依赖，加入 `static/` 和 `scripts/`，使用 PyInstaller 的 `--onefile --windowed` 生成程序。不复制用户浏览器资料。

支持 `--node`、`--cli-root`、`--work-dir`、`--output-dir` 指定构建路径。本地无 Node 许可证副本时，会从官方仓库获取对应版本许可证。

构建前退出待覆盖的 exe，或者指定新的输出目录。

## 本地接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/` | 本地页面 |
| GET | `/api/ping` | 应用名称和版本 `2.0.0` |
| GET | `/api/state` | 课程、作业、扫描进度、错误及连接提示 |
| GET | `/api/session` | 本地操作令牌 |
| POST | `/api/refresh` | 手动请求检查；忙碌时不额外排队 |
| POST | `/api/settings` | 保存下一次启动端口 |
| POST | `/api/stop` | 退出服务并断开本程序连接 |

POST 请求需要 `X-CourseBeacon-Token`。服务校验 Host；存在 Origin 时要求其匹配本地页面。页面不加载第三方脚本。

## 数据存储

默认保存在 `%LOCALAPPDATA%\CourseBeacon`：

| 文件 | 内容 |
| --- | --- |
| `coursebeacon.sqlite3` | 最近一次汇总快照 |
| `config.json` | 保存的端口 |
| `coursebeacon-v2.log` | 新版诊断日志 |
| `coursebeacon-v2.log.1` 等 | 轮转日志，单文件约 1 MB，最多 3 份备份 |
| `instance.lock` | 新版实例互斥锁文件 |
| `running-port.txt` | 当前实例端口记录 |
| `cli-sessions/` | CourseBeacon 专用 CLI 会话记录，避免其他 CLI 实例清理或争用 |

旧版独立 `chrome-profile` 目录不会被导入或删除。日常 Chrome 的登录状态继续保存在 Chrome 自己的资料目录中。

运行时的数据库、日志和 CLI 诊断文件可能包含个人课程信息，不应随源码或 exe 发布。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p test_app.py -v
```

12 项回归测试通过，覆盖手动刷新调度、重复点击抑制、登录失效停止、有限重试、验证阻塞、单实例锁、端口独占、仅断开浏览器连接、缓存更新、URL 校验及本地接口访问控制。

2026-09-30 实测新版初次扫描：排除 14 门已结束课程，30 门课程中 29 门读取成功，找到 5 项未完成作业；一门受网站人脸采集要求阻塞。闲置超过 5 分钟未自动启动新一轮。测试中发现并修复了 Windows 端口复用、CLI 会话记录干扰和重连会话名冲突。最终 exe 的启动扫描及随后手动触发的完整扫描均得到 29/30 门成功、5 项未完成作业的结果；扫描期间重复请求返回 `queued: false`，未额外排队。

真实页面联调需要 Chrome 授权连接，且超星账号具有课程访问权限。网页结构变化后应重新验证选择器及分页行为；本地回归测试不替代真实网站验证。

## 已知限制与常见问题

### 已开启远程调试但连接失败

确认开关位于日常使用的 Chrome 中，并允许 Chrome 的连接请求。程序页面给出连接提示后，可手动重试。受限执行环境或本机安全策略可能阻止读取 `DevToolsActivePort`；需在正常桌面用户环境中运行。

### 已登录 Chrome，为什么超星仍要求登录

Chrome 用户身份和超星网站登录是两件事。程序复用当前可连接 Chrome 实例中的网站会话，不能延长超星服务端的登录有效期。多个 Chrome 用户资料并存时，请确认已授权的实例就是登录超星的实例。

### 为什么没有自动更新剩余时间

v2 按要求仅在启动和手动点击时检查。页面显示的是最近一次检查时的原文，点击按钮才能重新读取。

### 为什么某课程读取失败

可能是人脸采集要求、登录失效、网络超时或网站结构变化。失败不等于没有作业；界面会报告未完成检查的情况。验证要求需本人在超星处理。

### 关闭网页后程序是否退出

不会。请使用“设置 → 退出 CourseBeacon”。该操作会保留个人 Chrome 和作业标签页。

### 兼容范围

当前适配根课程列表及已验证的新版作业页，不递归扫描课程文件夹。网站更改 DOM 后可能需要更新提取脚本。建议只运行一个 CourseBeacon 实例，并避免手动操作程序的扫描标签。

## 许可证与资源说明

项目尚未附带独立开源许可证，不在此声明源码采用 MIT 或 Apache-2.0。

- Playwright CLI 来自 Microsoft 的 `microsoft/playwright-cli`，工具自身许可证随运行时保留。
- Node 及其组件许可证随构建运行时保存。
- 作业行视觉规则与图标来自用户指定的超星页面，权益属于原权利人，用于本地界面还原。
