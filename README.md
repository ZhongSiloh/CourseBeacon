<img width="2560" height="1380" alt="image" src="https://github.com/user-attachments/assets/253d6a99-85d5-4875-b007-b6f840ce569d" /># CourseBeacon

> 基于 Python 与 Playwright CLI 的超星未完成作业汇总工具。

CourseBeacon 在本机启动网页服务，通过独立的 Google Chrome 会话读取超星课程中的未完成作业，并集中显示作业名称、提交状态、剩余时间和直达链接。程序可打包为 Windows 单文件 `.exe`，供未安装开发环境的用户使用。

## 目录

- [功能特性](#功能特性)
- [技术栈及其作用](#技术栈及其作用)
- [系统架构](#系统架构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [源码运行](#源码运行)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [实现步骤](#实现步骤)
- [本地接口](#本地接口)
- [数据存储](#数据存储)
- [打包发布](#打包发布)
- [测试与验证](#测试与验证)
- [已知限制](#已知限制)
- [常见问题](#常见问题)
- [许可证与资源说明](#许可证与资源说明)

## 功能特性

- **本地网页展示**：默认访问地址为 `http://127.0.0.1:17890`，支持自定义端口。
- **持久化浏览器会话**：使用 `--persistent` 和固定的 `--profile` 目录，复用独立 Chrome 中的登录状态。
- **等待手动登录**：遇到登录页时等待用户操作，课程列表出现后自动继续。
- **课程筛选**：排除卡片上明确标注“课程已结束”的课程。
- **未完成作业提取**：逐门进入“作业”，选择“未完成”，遍历作业分页并去重。
- **原网页风格**：按参考页面还原作业行的图标、字号、状态颜色、间距和时间样式。
- **直接打开作业**：使用页面中的真实作业链接，在新标签页打开。
- **自动与手动同步**：定期检查已发现课程，手动刷新时重新发现课程。
- **失败保留缓存**：单门课程读取失败时显示原因，保留该课程上次结果并标记待核验。
- **单文件发布**：内置 Python、Node.js 和 Playwright CLI 运行所需文件。

程序只读取和展示作业列表，不填写答案或提交作业。

## 技术栈及其作用

下表中的版本为本项目构建时使用的版本，不代表所有其他版本均已验证。

| 技术 / 模块 | 构建版本或形式 | 在项目中的作用 |
| --- | --- | --- |
| Python | 3.13.1，x64 | 程序入口、配置解析、后台扫描调度、缓存管理和本地服务 |
| `http.server` | Python 标准库 | 使用 `ThreadingHTTPServer` 和 `BaseHTTPRequestHandler` 提供静态文件及 JSON 接口 |
| `threading` | Python 标准库 | 将课程扫描与网页请求分开处理，通过锁和事件协调刷新、状态读取和退出 |
| `subprocess` | Python 标准库 | 以参数列表调用内置 Node 和 CLI，读取输出并处理超时 |
| Node.js | 24.15.0 | 运行官方 Playwright CLI 及其依赖 |
| `@playwright/cli` | 0.1.13 | 启动 Chrome、管理会话、执行 Playwright 页面提取脚本 |
| Google Chrome | 用户已安装的浏览器 | 提供真实登录界面、执行网页脚本、访问课程和打开作业 |
| SQLite / `sqlite3` | Python 内置接口 | 保存最近一次汇总快照，无需额外数据库服务 |
| HTML5 / CSS3 | 原生静态页面 | 构建 CourseBeacon 页面和作业行布局，适配窄屏 |
| JavaScript / Fetch API | 原生浏览器接口 | 轮询本地状态、渲染作业、保存设置、触发刷新和退出 |
| PyInstaller | 6.16.0 | 将 Python 程序、静态资源、提取脚本和 Node/CLI 运行时打包为 `.exe` |
| `unittest` | Python 标准库 | 验证缓存更新、失败保留、URL 校验和本地接口访问控制 |

当前代码采用 Python 标准库服务和原生前端，不依赖参考指南中的 FastAPI、Vue、Element Plus 或 Axios，也不要求安装 Python 版 Playwright。

## 系统架构

```text
用户
 └─ Chrome 中的 CourseBeacon 页面（127.0.0.1）
     └─ 本地 JSON 接口
         └─ Python 应用
             ├─ HTTP 服务：静态页面、状态查询、设置和退出
             ├─ SQLite：最近一次扫描快照
             └─ 后台扫描线程
                 └─ bridge.py：子进程调用
                     └─ Node.js → playwright-cli
                         └─ 独立 Chrome 会话
                             └─ 超星课程 → 作业 → 未完成
```

浏览器自动化命令由 `bridge.py` 串行执行。前端约每 1.5 秒读取一次**本地状态**；这不等于每 1.5 秒访问超星。超星课程扫描按后台同步周期执行。

## 环境要求

### 使用打包程序

- Windows 10/11 x64；本次构建及实测环境为 Windows 11 x64。
- 已安装 Google Chrome。
- 能正常访问超星，并拥有可查看课程的账号。
- 本地使用的端口未被其他程序占用。

不需要额外安装 Python、Node.js、npm 或 Playwright CLI。Chrome 不包含在安装包中。

### 源码开发与构建

- Python 3.13 x64。
- Node.js 与 npm；本项目使用 Node.js 24.15.0 构建。
- Google Chrome。
- `@playwright/cli@0.1.13`。
- `requirements-build.txt` 中列出的 PyInstaller。

## 快速开始

1. 双击发布的 `CourseBeacon-persistent.exe`。自行构建时，默认文件名为 `CourseBeacon.exe`。
2. 程序启动本地服务，并打开独立 Chrome 中的超星页和 CourseBeacon 页。
3. 首次使用时，在该 Chrome 窗口的超星登录页完成登录。
4. 等待课程扫描，汇总页面会逐步显示未完成作业。
5. 点击任意作业行，在新标签页进入对应作业。鼠标悬停可查看课程名称。
6. 使用“刷新作业”重新检查课程；使用“设置”修改下次启动端口。
7. 通过“设置 → 退出 CourseBeacon”结束程序及其创建的独立 Chrome 会话。

扫描期间请保留扫描标签页，避免在该标签页手动跳转。可以正常使用 CourseBeacon 页面及其打开的作业标签页。仅关闭网页标签不会结束后台服务。

## 源码运行

以下命令在解压后的源码根目录执行，使用 PowerShell。

### 1. 创建 Python 虚拟环境

```powershell
python -m venv .venv
```

### 2. 安装构建依赖及浏览器自动化工具

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
npm install -g @playwright/cli@0.1.13
```

Python 应用本身使用标准库；PyInstaller 主要用于生成可执行文件。

### 3. 准备 Node 和 CLI 运行时

```powershell
.\.venv\Scripts\python.exe build.py --prepare
```

此命令将本机已安装的 Node、Playwright CLI 及其依赖复制到 `build-work/runtime/`。如果本地没有 Node 许可证副本，构建脚本会从 Node 官方仓库获取对应版本许可证。

### 4. 指定运行时并启动

```powershell
$env:COURSEBEACON_NODE = "$PWD\build-work\runtime\node.exe"
$env:COURSEBEACON_CLI = "$PWD\build-work\runtime\cli\playwright-cli.js"

.\.venv\Scripts\python.exe app.py --port 17890
```

随后在程序打开的 Chrome 中登录超星。重新打开 PowerShell 后，源码运行所需的两个环境变量需要重新设置。

## 配置说明

### 命令行参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `-p` / `--port` | 配置文件中的端口，否则为 `17890` | 本地监听端口，范围 `1024–65535` |
| `--interval` | `60` | 每轮同步结束后等待的秒数，最小值为 `30` |
| `--data-dir` | `%LOCALAPPDATA%\CourseBeacon` | 数据库、日志、配置和默认浏览器资料目录的存放位置 |

```powershell
.\CourseBeacon-persistent.exe --port 9000 --interval 120
```

源码运行时同样支持这些参数：

```powershell
.\.venv\Scripts\python.exe app.py --port 9000 --data-dir ".\local-data"
```

端口选择优先级为：**命令行参数 → `config.json` → 默认端口**。页面中保存的端口在下次启动时生效；命令行指定端口不会自动改写配置文件。

`config.json` 示例：

```json
{
  "port": 17890
}
```

源码还包含用于开发验证的 `--profile`、`--session` 和 `--attach` 参数，日常使用无需设置。

### 会话持久化

实际启动参数包含：

```text
playwright-cli -s=coursebeacon open <超星首页URL> --browser=chrome --headed --persistent --profile=<固定资料目录> --raw
```

Python 通过参数列表执行该命令，不将 URL 拼接为 Shell 命令。

- `--persistent`：启用持久化浏览器会话。
- `--profile`：指定稳定的资料目录，默认是 `%LOCALAPPDATA%\CourseBeacon\chrome-profile`。
- `--headed`：显示浏览器窗口，便于用户完成登录。
- `--browser=chrome`：使用系统 Google Chrome。

持久化用于保留浏览器保存的登录状态，不代表登录永久有效。超星使会话过期或要求验证时，仍需本人重新操作。更换资料目录后不会自动继承原目录的登录状态。

## 项目结构

```text
CourseBeacon/
├─ app.py                    # HTTP 服务、扫描调度、配置与 SQLite 缓存
├─ bridge.py                 # Python 调用 Node / Playwright CLI
├─ build.py                  # 准备运行时与 PyInstaller 打包
├─ requirements-build.txt    # 构建依赖
├─ test_app.py               # 标准库 unittest 测试
├─ README.md                 # 项目说明
├─ scripts/
│  ├─ courses.js             # 课程发现与已结束课程筛选
│  └─ assignments.js         # 未完成作业筛选、分页及字段提取
├─ static/
│  ├─ index.html             # 页面结构
│  ├─ style.css              # 页面与作业行样式
│  ├─ app.js                 # 状态轮询和交互
│  ├─ icons-act.png          # 作业图标资源
│  └─ endTime.png            # 剩余时间图标
├─ build-work/               # 构建时生成，包含运行时和打包中间文件
└─ dist/                     # 构建时生成，存放 CourseBeacon.exe
```

## 实现步骤

### 1. 初始化配置和本地服务

`app.py` 解析命令行参数，确定数据目录和端口，创建日志及 SQLite 缓存表，读取上次快照。随后使用 `ThreadingHTTPServer` 绑定 `127.0.0.1`，提供页面和接口，并启动后台扫描线程。

缓存中的条目在重新核验前被标记为 `stale`，以区分历史结果与本次成功读取的数据。

### 2. 启动持久化 Chrome

`Bridge.open()` 调用内置 Node 执行 `playwright-cli open`，传入 `--persistent` 和固定 `--profile`。Chrome 首先访问超星个人空间，再在同一浏览器上下文中新建 CourseBeacon 标签页。

超星入口为：

```text
https://i.chaoxing.com/base?ws=3&vflag=true&fid=&backUrl=
```

### 3. 等待登录与课程列表加载

扫描线程执行 `scripts/courses.js`，遍历页面及 iframe，寻找 `#courseList`。列表尚未出现时，页面提示用户完成登录，并每隔约 2 秒重新检查。用户退出程序时结束等待。

### 4. 提取并筛选课程

`courses.js` 从 `#courseList > li.course` 读取课程 ID、名称和入口链接，排除 `.not-open-tip` 中包含“课程已结束”的卡片。筛选依据是页面的明确标记，而不是课程的日期或名称。

如果发现课程文件夹，当前版本会报告兼容限制，避免将根列表扫描结果当成完整结果。

### 5. 进入作业页并选择未完成

`assignments.js` 打开课程链接，点击“作业”入口，在页面或 iframe 中寻找 `.task-list #status`。如果当前筛选值不是 `1`，点击 `input[name="group-radio"][data="1"]`，并等待新文档中的 `#status` 确认变为 `1`。

等待筛选值变化可以避免点击后过早读取旧列表。人脸采集或登录失效等阻塞会转为可见错误。

### 6. 提取字段、遍历分页和去重

脚本从 `.bottomList > ul > li` 提取下列信息：

| 字段 | 用途 |
| --- | --- |
| `title` | 作业名称 |
| `status` | 原网页的提交状态文字 |
| `url` | 原网页提供的作业直达链接 |
| `timeText` | 原网页剩余时间文本 |
| `timeActive` | 是否使用进行中时间的显示样式 |
| `timeIcon` / `iconClass` | 时间图标信息和作业图标类别 |
| `label` | 原网页的附加标签 |
| `observedAt` | 此条数据的读取时间，毫秒时间戳 |

存在可用“下一页”按钮时继续读取，等待列表内容变化后再提取。单门课程使用 URL 去重，并设置最多 200 页的保护上限；超过上限时报告失败。

Python 随后补充条目 ID、所属课程及缓存标记，并校验链接属于超星域名。

### 7. 更新结果与保存快照

每门课程成功读取后，用新结果替换该课程的旧条目。如果确认该课程没有未完成作业，其旧条目会被移除。

单门课程失败时，保留该课程的旧条目并标记 `stale`，同时记录错误；其他课程继续扫描。一轮结束后将汇总状态保存为 SQLite 中的 JSON 快照。

### 8. 渲染页面和作业链接

前端 `static/app.js` 轮询 `/api/state`，使用 DOM API 和 `textContent` 构建作业行。作业标题、状态及时间分别放入对应样式区域，链接以新标签页打开。

样式采用原网页的标题字号、灰色状态、橙色剩余时间和作业图标，去除参考截图中用于标注的红框。课程名称放在悬停提示中。
<img width="2560" height="1380" alt="屏幕截图 2026-09-30 103627" src="https://github.com/user-attachments/assets/bec9fc2d-141b-406f-b928-08b9af9c75e3" />



### 9. 自动刷新与退出

一轮同步结束后等待 `--interval` 指定的时间，再读取已发现课程。自动同步优先复用作业列表链接；链接读取失败时，重新从课程入口获取。手动刷新会重新发现课程并清空列表链接缓存。

点击“退出 CourseBeacon”后，程序发出停止信号，关闭 HTTP 服务，并由后台线程结束本程序创建的 Chrome 会话。

> **时间显示说明：** `timeText` 直接使用超星列表返回的原文，不在前端按秒倒计时，也不推算精确截止时刻。与刚刷新的超星页面之间可能存在扫描耗时及同步间隔造成的差异。前端频繁轮询本地状态不会自动刷新超星时间文本。

## 本地接口

接口仅供本机 CourseBeacon 页面使用。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/` | 返回 CourseBeacon 页面 |
| `GET` | `/api/ping` | 返回应用名称和版本 |
| `GET` | `/api/state` | 返回扫描状态、课程、作业、错误和进度 |
| `GET` | `/api/session` | 返回当前进程的本地操作令牌 |
| `POST` | `/api/refresh` | 请求重新发现课程并同步 |
| `POST` | `/api/settings` | 接收 `{"port":9000}`，保存下次启动端口 |
| `POST` | `/api/stop` | 请求退出程序 |

POST 请求需要 `X-CourseBeacon-Token` 请求头。服务校验 `Host`；请求携带 `Origin` 时要求其匹配本地页面来源。静态页面采用同源内容策略，不加载第三方脚本。

## 数据存储

默认数据目录为 `%LOCALAPPDATA%\CourseBeacon`：

```text
CourseBeacon/
├─ chrome-profile/          # 独立 Chrome 资料及登录状态
├─ coursebeacon.sqlite3     # 最近一次汇总快照
├─ config.json              # 保存的端口配置
└─ coursebeacon.log         # 扫描及异常日志
```

CLI 还可能在工作目录生成诊断文件；正常执行完成后，Python 会删除本次生成的临时命令脚本。

SQLite 使用单张缓存表：

```sql
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

当前以 `snapshot` 为键保存一份 JSON 快照，不是逐次保留的历史作业数据库。运行时数据保存在用户数据目录，和 PyInstaller 的临时解压目录分开。

运行后的资料目录包含登录状态及个人课程信息，不应打包发布。项目构建脚本只收集程序文件、静态资源、提取脚本和工具运行时。

## 打包发布

### 标准构建

在源码根目录执行：

```powershell
.\.venv\Scripts\python.exe build.py
```

输出文件：

```text
dist/CourseBeacon.exe
```

当前提供的持久化版本发布文件名为 `CourseBeacon-persistent.exe`；文件名不同不影响启动参数或数据目录。

### 自定义构建路径

以下为路径格式示例，需替换成本机实际安装位置：

```powershell
.\.venv\Scripts\python.exe build.py `
  --node "C:\Program Files\nodejs\node.exe" `
  --cli-root "$env:APPDATA\npm\node_modules\@playwright\cli" `
  --work-dir ".\build-work" `
  --output-dir ".\dist"
```

### 打包过程

1. 定位 Node 可执行文件及已安装的 Playwright CLI。
2. 复制 Node、CLI 和其依赖，记录版本并准备许可证文件。
3. 通过 PyInstaller 分析 `app.py` 及 Python 依赖。
4. 将 `static/`、`scripts/` 和准备好的 `runtime/` 加入包中。
5. 使用 `--onefile --windowed` 生成无控制台窗口的单文件程序。

程序通过 `sys._MEIPASS` 定位打包资源；源码运行时则使用源码目录。构建前请退出需要覆盖的旧 `.exe`，否则 Windows 可能阻止替换文件。

## 测试与验证

### 自动化测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p test_app.py -v
```

当前 4 项测试覆盖：

- 超星 URL 白名单及不安全地址拒绝。
- 单门课程失败时保留其缓存，成功课程按新结果更新。
- 完整刷新后移除失效课程条目，并保存新的快照。
- 本地接口令牌、来源、Host 校验及端口配置校验。

这些测试不要求登录超星，不调用真实课程页面。

### 开发阶段人工与浏览器验证

已验证过真实账号的课程扫描、作业直达链接、登录等待、端口设置、窄屏布局和程序退出；隔离浏览器场景也验证了课程排除、未完成筛选、多页遍历及时间原文提取。

这类验证依赖当时的超星页面结构。更新选择器或浏览器工具版本后，应重新验证实际课程页面。最新持久化构建已核验打包代码包含 `--persistent` 参数。

## 已知限制

- 当前适配“我学的课”根课程列表和开发时验证过的新版作业页，不递归扫描课程文件夹。
- 课程被人脸采集、登录验证或其他访问要求阻塞时，需要本人在超星官方页面或 APP 处理。
- 超星调整 DOM、筛选方式或分页结构后，可能需要更新 `scripts/` 中的选择器。
- 剩余时间按同步时读取到的原文展示，不保证与另一张刚刷新的网页逐秒一致。
- 自动刷新检查已经发现的课程；新增或移出的课程通过手动刷新或重新启动重新发现。
- 关闭 Chrome、在扫描标签页手动导航或同时启动共用资料目录的多个实例，可能干扰扫描。建议同一时间运行一个实例。
- 本地服务面向单机使用，不提供公网部署或多用户账户管理。

## 常见问题

### 为什么需要再登录一次？

程序使用独立 Chrome 资料目录，不自动读取日常 Chrome 的登录状态。首次登录后会通过持久化目录复用；服务端使会话过期时仍需重新登录。

### 为什么提示端口被占用？

可能已有 CourseBeacon 实例或其他程序使用该端口。退出旧实例，或通过 `--port` 指定其他端口。程序不会自动结束占用端口的其他进程。

### 页面关闭后程序还在运行吗？

会。网页只是操作界面，后台服务仍可能运行。应通过“设置 → 退出 CourseBeacon”退出。

### 读取失败等于没有未完成作业吗？

不等于。程序会分别显示失败课程及原因，并保留可用旧结果。只有成功完成扫描且结果为空时，才展示对应的无作业状态。

### 为什么构建时找不到运行时？

先确认 Node 和 `@playwright/cli` 已安装，再执行 `build.py --prepare`。源码运行还需要设置 `COURSEBEACON_NODE` 和 `COURSEBEACON_CLI`。路径不在默认位置时，使用构建参数显式指定。

### 日志在哪里？

默认位于 `%LOCALAPPDATA%\CourseBeacon\coursebeacon.log`。使用 `--data-dir` 后，日志随数据目录改变。反馈问题前应移除日志中的个人信息和带签名的课程链接。

## 许可证与资源说明

项目尚未附带单独的开源许可证文件，因此此 README 不声明项目源码采用 MIT、Apache-2.0 或其他开源许可证。

- Playwright CLI 来源于 Microsoft 的 `microsoft/playwright-cli` 项目，其 Apache-2.0 许可证随工具运行时保留。
- Node 及其所包含组件的许可证随构建运行时保存。
- 作业行视觉规则及 `icons-act.png`、`endTime.png` 来自用户指定的超星作业页面，用于本地汇总界面的样式还原；资源权益属于原权利人。
