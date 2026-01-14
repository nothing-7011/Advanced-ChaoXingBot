# :computer: 超星学习通自动化完成任务点(命令行版)

<p align="center">
    <a href="https://github.com/Samueli924/chaoxing" target="_blank" style="margin-right: 20px; font-style: normal; text-decoration: none;">
        <img src="https://img.shields.io/github/stars/Samueli924/chaoxing" alt="Github Stars" />
    </a>
    <a href="https://github.com/Samueli924/chaoxing" target="_blank" style="margin-right: 20px; font-style: normal; text-decoration: none;">
        <img src="https://img.shields.io/github/forks/Samueli924/chaoxing" alt="Github Forks" />
    </a>
    <a href="https://github.com/Samueli924/chaoxing" target="_blank" style="margin-right: 20px; font-style: normal; text-decoration: none;">
        <img src="https://img.shields.io/github/languages/code-size/Samueli924/chaoxing" alt="Code-size" />
    </a>
    <a href="https://github.com/Samueli924/chaoxing" target="_blank" style="margin-right: 20px; font-style: normal; text-decoration: none;">
        <img src="https://img.shields.io/github/v/release/Samueli924/chaoxing?display_name=tag&sort=semver" alt="version" />
    </a>
</p>

:muscle: 本项目的最终目的是通过开源消灭所谓的付费刷课平台，希望有能力的朋友都可以为这个项目提交代码，支持本项目的良性发展

:star: 觉得有帮助的朋友可以给个Star

## :rocket: 快速开始

### 1. 源码运行
1. `git clone --depth=1 https://github.com/Samueli924/chaoxing` 项目至本地
2. `cd chaoxing`
3. `pip install -r requirements.txt` 或者 `pip install .` (通过 pyproject.toml 安装依赖)
4. **推荐**: 复制 `config_template.ini` 为 `config.ini`，并参照下文配置。
5. 运行: `python main.py` (会自动读取 `config.ini`)
   - 也可以使用命令行参数: `python main.py -u 手机号 -p 密码 -l 课程ID1,课程ID2`

### 2. 打包文件运行 (Windows)
1. 从 [Releases](https://github.com/Samueli924/chaoxing/releases) 下载最新 exe 文件。
2. 将 `config_template.ini` 下载并重命名为 `config.ini`，放在 exe 同级目录并配置。
3. 双击运行 exe，或在命令行运行: `./chaoxing.exe`

### 3. Docker 运行
```bash
# 构建
docker build -t chaoxing .

# 运行 (挂载配置文件)
docker run -it -v /你的路径/config.ini:/config/config.ini chaoxing
```

---

## :gear: 配置指南

所有配置项均在 `config.ini` 中设置。建议复制 `config_template.ini` 并修改。

### 1. 基础配置 `[common]`
| 选项 | 说明 |
| --- | --- |
| `use_cookies` | 设为 `true` 则尝试从 `cookies.txt` 登录，忽略账号密码 |
| `username` | 学习通手机号 |
| `password` | 学习通密码 |
| `course_list` | 指定学习的课程 ID (逗号分隔)，留空则学习所有课程 |
| `speed` | 视频倍速 (默认 1，最大 2) |
| `jobs` | 并发章节数 (默认 4) |
| `notopen_action` | 遇到关闭任务点的行为: `retry`(重试), `ask`(询问), `continue`(跳过) |

### 2. 题库配置 `[tiku]`
用于自动完成章节检测、测验等答题任务。

*   `provider`: 题库提供方 (详情见下文)。
*   `submit`:
    *   `true`: 答题并提交 (只有达到 `cover_rate` 覆盖率才会提交，否则只保存)。
    *   `false`: 只答题并保存，**不提交**。
*   `cover_rate`: 最低题库覆盖率 (0.0 - 1.0)，达到此比例才允许提交。

#### 支持的题库 (Provider)
*   `TikuYanxi`: 言溪题库 (需配置 `tokens`)
*   `TikuLike`: LIKE知识库 (需配置 `tokens`, `likeapi_*` 选项)
*   `TikuAdapter`: [tikuAdapter](https://github.com/DokiDoki1103/tikuAdapter) 项目 (需配置 `url`)
*   `SiliconFlow`: 硅基流动 AI (需配置 `siliconflow_key`, `siliconflow_model`)
*   `AI`: **AI 大模型答题 (Gemini)** (详见下文)

---

## :sparkles: AI 大模型答题 (Gemini)

本项目新增了基于 Google Gemini 的多模态 AI 答题功能，支持图文识别与智能推理。
旨在于解决学习通题目中间包含莫名其妙的html 图片标签而大模型不能自主识别的问题。
原项目仅支持“自测试题”栏目下的题目获取，尽管其他小节（比如“教学内容”）的题目也有被收集，但是选项信息完全对不上，目前没有解决这个问题（程序也不会保存或者提交这些题目的答案）。

你可以用cluster_manager.py来管理下载到的题库包：
1. 确认你的题库包含questions.json，plain_questions.json和answers.json
2. 解压到data/sets/下
3. only_fetch_questions设置为true，运行主程序
4. 等到程序提示完成了题目获取之后，运行cluster_manager.py
5. 完成之后将only_fetch_questions设置为false，运行主程序，这次运行时主程序会用题库的结果一次性处理所有习题

### 配置方法
1.  在 `[tiku]` 中设置 `provider = AI`。
2.  配置 `[parser]` (用于解析题目图片) 和 `[solver]` (用于推理答案)。

```ini
[tiku]
provider = AI
submit = true  ; 是否自动提交，可以设false

[parser]
; 用于解析题目图片的 Gemini API Key (必须支持 Vision，如 gemini-2.0-flash，实际上只需要有gemini-2.5-flash-lite的多模态能力就可以了)
gemini_api_key = xxxxxxx
model = gemini-2.0-flash

[solver]
; 用于推理答案的 Gemini API Key (这里可以用CLIProxyAPI转接一个纯文本模型，如 deepseek-reasoner，以我的概率论课程习题为例，用gemini-3-pro-preview直接一遍全对了)
gemini_api_key = xxxxxxx
model = gemini-2.0-flash
request_interval = 2.0  ; 请求间隔(秒)，避免触发限流
```

### :warning: 使用流程 (重要)

由于 AI 答题包含 "收集题目 -> 解析图片 -> 推理答案" 的耗时过程，你需要**运行程序两次**才能完成提交：

1.  **第一次运行**:
    *   程序会遍历课程，收集所有题目到 `data/{courseId}/questions.json`。
    *   遍历结束后，自动启动 **Parser Agent** 解析题目中的图片。
    *   随后启动 **Solver Agent** 进行推理，生成答案并保存到 `data/{courseId}/answers.json`。
    *   *此时任务点尚未提交*。

2.  **第二次运行**:
    *   程序再次遍历课程，读取上一步生成的 `answers.json`。
    *   如果答案完整，则自动填入并提交任务点。

> **注意**: 请确保你的网络环境可以连接 Google Gemini API，或在配置中设置反代 `endpoint`。

---

## :bell: 通知配置 `[notification]`
任务完成后发送通知。

*   `provider`: 支持 `ServerChan`, `Qmsg`, `Bark`, `Telegram`。
*   `url`: 对应的 Webhook URL 或 API 地址。
*   `tg_chat_id`: Telegram 专用 Chat ID。

---

## :heart: CONTRIBUTORS

![Alt](https://repobeats.axiom.co/api/embed/d3931e84b4b2f17cbe60cafedb38114bdf9931cb.svg "Repobeats analytics image")  

<a style="margin-top: 15px" href="https://github.com/Samueli924/chaoxing/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Samueli924/chaoxing" />
</a>

## :warning: 免责声明
- 本代码遵循 [GPL-3.0 License](https://github.com/Samueli924/chaoxing/blob/main/LICENSE) 协议。
- 本代码仅用于**学习讨论**，禁止**用于盈利**。
- 他人或组织使用本代码进行的任何**违法行为**与本人无关。
