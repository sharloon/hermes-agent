hermes所有的能力列表

这是一个极其完整的 AI Agent 框架，以下是 Hermes 所有能力的完整清单：                                                                                                 
                                                                                                                                                                      
 ---                                                                                                                                                                  
 Hermes Agent 完整能力清单                                                                                                                                            
                                                                                                                                                                      
 ---                                                                                                                                                                  
 一、核心架构                                                                                                                                                         
                                                                                                                                                                      
 运行模式：                                                                                                                                                           
 - hermes CLI — 交互式终端 UI（Rich + prompt_toolkit）                                                                                                                
 - hermes gateway — 消息平台守护进程                                                                                                                                  
 - hermes api — OpenAI 兼容 HTTP API 服务器                                                                                                                           
 - hermes web — Web 管理界面
 - ACP Server — 编辑器集成（VS Code、Zed、JetBrains）                                                                                                                 
 - Batch Runner — 并行轨迹生成（训练数据）                                                                                                                            
 - Cron Scheduler — 定时自动化任务                                                                                                                                    
                                                                                                                                                                      
 ---
 二、Agent 能力

 多 Agent 模式

 - 父代理通过 delegate_task 工具生成子代理
 - 支持并行执行（默认最多 3 个并发子代理）
 - 深度限制 2 层，防止无限递归
 - 子代理拥有独立上下文、工具集、迭代预算（默认 50 次）
 - Mixture of Agents（MoA）多模型协同推理

 推理与思考

 - Extended Thinking（Claude 思考模式）
 - 推理级别：none / minimal / low / medium / high / xhigh
 - 可显示/隐藏推理过程

 上下文管理

 - 自动上下文压缩（LLM 摘要）
 - Anthropic Prompt Caching
 - 项目上下文文件注入
 - FTS5 全文会话搜索 + LLM 摘要

 ---
 三、工具系统（60+ 工具）

 文件操作

 read_file / write_file / patch / search_files

 Web 与浏览器

 web_search / web_extract / browser_navigate / browser_snapshot / browser_click / browser_type / browser_scroll / browser_back / browser_press / browser_get_images /
 browser_vision / browser_console

 浏览器后端：Browserbase / Browser Use / Camofox / Firecrawl

 终端与代码

 terminal（6 种后端）/ process（后台进程管理）/ execute_code（沙箱执行）

 终端后端：Local / Docker / SSH / Modal / Daytona / Singularity

 记忆与规划

 memory / todo / session_search

 技能管理

 skills_list / skill_view / skill_manage（创建/编辑/删除）

 多媒体

 vision_analyze / image_generate / text_to_speech（Edge TTS / ElevenLabs / OpenAI）/ 转录工具

 调度与消息

 cronjob / send_message（跨平台发送）

 智能家居

 ha_list_entities / ha_get_state / ha_list_services / ha_call_service

 其他

 clarify（向用户提问）/ delegate_task（子代理）/ mixture_of_agents / RL 训练工具（10 个）

 ---
 四、Skill 系统（100+ 技能）

 内置技能分类

 ┌──────────────┬──────────────────────────────────────────────────────────────────────────────────────────┐
 │     分类     │                                           技能                                           │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ Apple 集成   │ apple-notes, apple-reminders, findmy, imessage                                           │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ 自主 AI 代理 │ claude-code, codex, hermes-agent, opencode                                               │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ 创意         │ ascii-art, manim-video, p5js, songwriting-and-ai-music, excalidraw                       │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ 数据科学     │ jupyter-live-kernel                                                                      │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ GitHub       │ github-auth, github-code-review, github-issues, github-pr-workflow                       │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ MLOps        │ axolotl, vllm, llama-cpp, stable-diffusion, whisper, huggingface-hub, weights-and-biases │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ 生产力       │ google-workspace, notion, linear, powerpoint, obsidian                                   │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ 研究         │ arxiv, research-paper-writing, polymarket, blogwatcher                                   │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ 软件开发     │ plan, test-driven-development, systematic-debugging, subagent-driven-development         │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ 社交媒体     │ xitter                                                                                   │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ 安全         │ godmode（红队）                                                                          │
 ├──────────────┼──────────────────────────────────────────────────────────────────────────────────────────┤
 │ MCP          │ mcporter, native-mcp                                                                     │
 └──────────────┴──────────────────────────────────────────────────────────────────────────────────────────┘

 技能生命周期

 - Agent 可自主创建、编辑、删除技能
 - 安全扫描（skills_guard.py）
 - 集成 Skills Hub（agentskills.io）社区市场
 - 通过 /skill-name 命令调用

 ---
 五、MCP 支持

 - 支持 stdio 传输（本地进程）
 - 支持 HTTP/SSE 传输（远程服务器）
 - 自动重连 + 指数退避
 - 工具动态发现与注册
 - Sampling 支持（MCP 服务器可请求 LLM 补全）
 - CLI 管理：hermes mcp add/remove/list/test

 ---
 六、消息平台（18 个平台）

 ┌────────────────┬───────────────────────────────┐
 │      平台      │             说明              │
 ├────────────────┼───────────────────────────────┤
 │ Telegram       │ Bot 命令、DM 配对、群组、语音 │
 ├────────────────┼───────────────────────────────┤
 │ Discord        │ Slash 命令、线程、嵌入        │
 ├────────────────┼───────────────────────────────┤
 │ Slack          │ Slash 命令、线程、文件上传    │
 ├────────────────┼───────────────────────────────┤
 │ WhatsApp       │ 个人消息、媒体                │
 ├────────────────┼───────────────────────────────┤
 │ Signal         │ 加密消息、群组                │
 ├────────────────┼───────────────────────────────┤
 │ Email          │ IMAP/SMTP                     │
 ├────────────────┼───────────────────────────────┤
 │ Matrix         │ 去中心化加密消息              │
 ├────────────────┼───────────────────────────────┤
 │ Mattermost     │ 自托管团队消息                │
 ├────────────────┼───────────────────────────────┤
 │ DingTalk       │ 钉钉（阿里巴巴）              │
 ├────────────────┼───────────────────────────────┤
 │ Feishu/Lark    │ 飞书（字节跳动）              │
 ├────────────────┼───────────────────────────────┤
 │ WeChat/Weixin  │ 微信个人版                    │
 ├────────────────┼───────────────────────────────┤
 │ WeCom          │ 企业微信                      │
 ├────────────────┼───────────────────────────────┤
 │ QQBot          │ QQ 官方机器人 API v2          │
 ├────────────────┼───────────────────────────────┤
 │ BlueBubbles    │ Apple iMessage                │
 ├────────────────┼───────────────────────────────┤
 │ SMS            │ Twilio                        │
 ├────────────────┼───────────────────────────────┤
 │ Home Assistant │ 智能家居事件                  │
 ├────────────────┼───────────────────────────────┤
 │ Webhook        │ 通用 Webhook                  │
 ├────────────────┼───────────────────────────────┤
 │ API Server     │ OpenAI 兼容 HTTP API          │
 └────────────────┴───────────────────────────────┘

 ---
 七、对外 API 接口

 OpenAI 兼容端点

 - POST /v1/chat/completions
 - POST /v1/responses
 - GET /v1/models
 - POST /v1/runs + GET /v1/runs/{id}/events（SSE）

 Web 管理 API（30+ 端点）

 - /api/sessions/* — 会话管理
 - /api/config/* — 配置管理
 - /api/skills/* — 技能管理
 - /api/tools/* — 工具管理
 - /api/cron/* — 定时任务
 - /api/env/* — 环境变量
 - /api/oauth/* — OAuth 认证
 - /api/mcp/* — MCP 服务器管理
 - /api/analytics/* — 使用分析

 ---
 八、Web UI

 - React 19 + Vite + TypeScript + Tailwind CSS
 - 配置管理、会话浏览与搜索
 - 技能管理、工具配置
 - 定时任务管理、OAuth 集成
 - 使用分析仪表盘
 - 默认地址：http://127.0.0.1:9119

 ---
 九、长期记忆（8 个提供商）

 内置记忆：
 - MEMORY.md — 持久化声明式记忆
 - USER.md — 用户档案
 - FTS5 跨会话全文搜索

 外部提供商（可插拔）：
 Honcho / Hindsight / Holographic / Mem0 / Byterover / OpenViking / RetainDB / Supermemory

 ---
 十、模型提供商（20+）

 Nous Portal / Anthropic / OpenAI / Google Gemini / OpenRouter（200+ 模型）/ Grok / Qwen / Kimi / MiniMax / StepFun / Groq / Perplexity / Together AI / NVIDIA / Arcee
  / Hugging Face / Ollama（本地）/ vLLM（本地）/ GitHub Copilot / Xiaomi MiMo

 ---
 十一、安全与权限

 - 危险命令审批机制（交互式确认）
 - YOLO 模式（跳过审批，可选）
 - 路径安全验证
 - URL 安全检查
 - OSV 漏洞扫描
 - Tirith 安全集成
 - 凭证文件保护
 - CORS 限制（仅 localhost）

 ---
 十二、其他高级特性

 - 多配置文件：完全隔离的多实例支持
 - 定时任务：Cron 表达式调度，支持技能执行
 - 主题系统：default / ares / mono / slate + 自定义皮肤
 - 编辑器集成：VS Code / Zed / JetBrains（ACP 协议）
 - 训练数据生成：轨迹保存 + Batch Runner
 - RL 训练：Tinker-Atropos 环境集成
 - Fast Mode：快速响应模式
 - 语音模式：TTS + 语音输入
 - 国际化：i18n 支持

 ---

#目录结构说明（二次开发参考）

 ~/hermes-agent/
 ├── run_agent.py          # 核心 Agent 循环（AIAgent 类）
 ├── cli.py                # TUI 界面（HermesCLI 类）
 ├── model_tools.py        # 工具编排与分发
 ├── toolsets.py           # 工具集定义
 │
 ├── agent/                # Agent 内部模块
 │   ├── prompt_builder.py # 系统提示构建
 │   ├── memory_manager.py # 记忆管理
 │   └── context_engine.py # 上下文管理
 │
 ├── tools/                # 60+ 工具实现
 │   ├── file_tools.py
 │   ├── web_tools.py
 │   ├── terminal_tool.py
 │   └── delegate_tool.py  # 多 Agent 委托
 │
 ├── gateway/              # 消息平台网关
 │   └── platforms/        # 各平台适配器
 │
 ├── hermes_cli/           # CLI 与 Web 服务
 │   ├── main.py           # 入口
 │   ├── web_server.py     # FastAPI 后端
 │   └── web_dist/         # 前端构建产物（构建后生成）
 │
 ├── web/                  # React 前端源码
 │   ├── src/
 │   └── vite.config.ts    # 代理配置指向 :9119
 │
 ├── plugins/memory/       # 记忆提供商插件
 ├── cron/                 # 定时任务调度器
 └── ~/.hermes/            # 运行时数据（在 home 目录）
     ├── .env              # API Keys
     ├── config.yaml       # 主配置
     ├── SOUL.md           # Agent 人格定义
     ├── MEMORY.md         # 持久化记忆索引
     └── skills/           # 用户技能库


 # 总结一句话：Hermes 是一个企业级、全平台、自我进化的 AI Agent 框架，覆盖从个人助手到多平台自动化的完整场景。


