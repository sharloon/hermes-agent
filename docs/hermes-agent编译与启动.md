
 Hermes Agent — WSL2 源码编译完整启动指南

 环境要求

 ┌─────────┬───────────────────┬─────────────────────────┐
 │  依赖   │       版本        │          说明           │
 ├─────────┼───────────────────┼─────────────────────────┤
 │ WSL2    │ Ubuntu 22.04 推荐 │ 原生 Windows 不支持     │
 ├─────────┼───────────────────┼─────────────────────────┤
 │ Python  │ 3.11+             │ 必须                    │
 ├─────────┼───────────────────┼─────────────────────────┤
 │ Node.js │ 22 LTS            │ 前端构建必须            │
 ├─────────┼───────────────────┼─────────────────────────┤
 │ uv      │ 最新              │ Python 包管理器（推荐） │
 ├─────────┼───────────────────┼─────────────────────────┤
 │ Git     │ 任意              │ 版本管理                │
 ├─────────┼───────────────────┼─────────────────────────┤
 │ ripgrep │ 可选              │ 文件搜索加速            │
 └─────────┴───────────────────┴─────────────────────────┘


 第一步：WSL2 系统依赖

 # 更新系统

 sudo apt update && sudo apt upgrade -y

 # 安装基础构建工具
 sudo apt install -y \
     build-essential \
     python3-dev \
     python3-pip \
     libffi-dev \
     git \
     curl \
     ripgrep \
     ffmpeg

 # 安装 uv（快速 Python 包管理器）

 curl -LsSf https://astral.sh/uv/install.sh | sh
 source ~/.bashrc   # 或 source ~/.zshrc

 # 验证
 uv --version

 ---
 第二步：安装 Python 3.11

 # 用 uv 安装 Python 3.11（无需 sudo）
 uv python install 3.11

 # 验证
 uv python find 3.11

 
 第三步：安装 Node.js 22 (nvm方式)

 # 用 nvm 安装（推荐，方便版本管理）
curl -o- https://gitee.com/RubyMetric/nvm-cn/raw/main/install.sh | bash

source ~/.bashrc

 nvm install 22
 nvm use 22
 nvm alias default 22
 
  # 验证
 node --version   # v22.x.x
 npm --version



 第四步：获取源码

 # git clone https://github.com/NousResearch/hermes-agent.git ~/hermes-agent
 # cd ~/hermes-agent

 ▎ 重要：强烈建议把代码放在 WSL2 的 Linux 文件系统（~/）下，而不是 /mnt/g/ 这样的 Windows 挂载路径。跨文件系统 I/O 会导致 npm install 和 Python 包安装慢 10 倍以上。

 
第五步：创建 Python 虚拟环境并安装依赖
```shell

 cd ~/hermes-agent

 # 创建虚拟环境（Python 3.11）
 uv venv venv --python 3.11

 # 激活虚拟环境
 source venv/bin/activate

 # 安装完整依赖（包含 web、cron、mcp、messaging 等所有 extras）
 uv pip install -e ".[all]"

 # 验证安装
 hermes --version

 如果 [all] 安装失败（某些可选依赖有平台限制），可以只装核心 extras：

 uv pip install -e ".[web,cron,mcp,pty,messaging,cli,honcho]"
```


 第六步：构建前端（React/Vite）

```shell
cd ~/hermes-agent/web

# 安装前端依赖
npm install

# 构建生产版本（产物输出到 hermes_cli/web_dist/）
npm run build

# 验证构建产物
ls ../hermes_cli/web_dist/
```

> 开发模式（热更新）：`npm run dev`，前端监听 http://localhost:5173，自动代理 API 请求到后端 :9119。


 第七步：初始化配置

```shell
# 激活虚拟环境（如未激活）
source ~/hermes-agent/venv/bin/activate

# 运行交互式配置向导（选择模型、工具集、终端后端等）
hermes setup

# 或手动检查配置状态
hermes status

# 配置文件位于 ~/.hermes/config.yaml，可直接编辑
# 例如修改默认模型：
hermes config set model.default anthropic/claude-sonnet-4-6
也可以直接进入到配置文件修改
vim ~/.hermes/config.yaml --> model:xxx
或者在dashboard的CONFIG页面直接配置, api-key也一样（KEYS页面）
```


 第八步：启动服务

```shell
# 激活虚拟环境（如未激活）
source ~/hermes-agent/venv/bin/activate

# 启动 dashboard(包含前端和后端) 
hermes dashboard --host 0.0.0.0 --insecure

# 启动后台网关服务（Telegram/Slack/Email 等消息平台）
hermes gateway install   # 安装为系统服务
hermes gateway start/stop     # 启动服务
hermes gateway status    # 查看状态
```

