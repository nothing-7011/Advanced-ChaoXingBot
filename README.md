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

### 源码运行
1. `git clone --depth=1 https://github.com/nothing-7011/Advanced-ChaoXingBot` 项目至本地
2. `cd chaoxing`
3. `pip install -r requirements.txt` 或者 `pip install .` (通过 pyproject.toml 安装依赖)
4. **推荐**: 复制 `config_template.ini` 为 `config.ini`，并参照下文配置。
5. 运行: `python main.py` (会自动读取 `config.ini`)
   - 也可以使用命令行参数: `python main.py -u 手机号 -p 密码 -l 课程ID1,课程ID2`

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
*   `AI`: **AI 大模型答题 (Gemini / OpenAI Compatible)** (详见下文)

---

## :sparkles: AI 大模型答题 (Gemini / OpenAI Compatible)

本项目新增了多模态 AI 答题功能，支持图文识别与智能推理。
`[parser]` 和 `[solver]` 都支持两种协议：
- `gemini_v1beta`: 使用 `google-genai` SDK，对接 Gemini V1beta 兼容端点
- `openai_compatible`: 使用 `/v1/chat/completions` 风格接口

如果使用 `gemini_v1beta`，需要提供 Gemini V1beta 兼容端点；如果使用 `openai_compatible`，需要提供 OpenAI Compatible 端点。
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
api_type = gemini_v1beta
api_key = xxxxxxx
model = gemini-2.0-flash
endpoint = https://generativelanguage.googleapis.com

[solver]
api_type = openai_compatible
api_key = xxxxxxx
model = gpt-5.4
endpoint = https://your-endpoint.example/v1
request_interval = 2.0  ; 请求间隔(秒)，避免触发限流
```

也可以让两个 Agent 都走同一种协议，只要端点支持对应能力即可。

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

> **注意**: `gemini_v1beta` 需要 Gemini V1beta 兼容端点，`openai_compatible` 需要 `/v1/chat/completions` 兼容端点。图片解析是否可用取决于对应端点是否支持视觉输入。

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
