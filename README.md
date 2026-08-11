# 三省六部 · Edict-Codex

> 将 [cft0808/edict](https://github.com/cft0808/edict)（MIT License）复刻为
> Codex 驱动的多 Agent 任务协作系统：服务端看板 + 三省六部编排协议 + 数据与代码双回滚保障。

原项目以 OpenClaw 为任务执行层；本复刻将执行层换成 Codex 会话：太子（主会话）收旨后按
「中书规划 → 门下审议 → 尚书派发 → 六部执行 → 回奏」逐级 spawn 子 agent，看板写操作统一走
`scripts/kanban_update.py` CLI 或 HTTP API。服务端保持零第三方依赖（Python 标准库），本机 Windows 直接跑。

## 架构

- 服务层：`dashboard/server.py` 提供看板 SPA + HTTP API + 状态机 + 审计日志 + 技能管理 +
  早朝新闻定时采集 + 朝堂议政，数据全部落 `data/*.json`，不做任务执行。
- 执行层：Codex 会话。`AGENTS.md` 是本项目太子工作协议；`agents/<id>/SOUL.md` 是 12 个角色模板；
  `agents.json` 是角色与权限矩阵（allowAgents）。
- 数据层：`data/tasks_source.json`（任务）、`agent_config.json`（模型配置）、
  `audit_log.json`（审计）、`dispatch_queue.json`（看板→Codex 唤醒队列）、
  `data/backups/`（快照轮转，保留最近 10 份）。

## 角色与流程

| 角色 | ID | 职责 |
|---|---|---|
| 太子 | `taizi` | 收旨分拣：闲聊直接回复，正式旨意建任务并转中书省 |
| 中书省 | `zhongshu` | 起草 ≤500 字执行方案 |
| 门下省 | `menxia` | 四维审议（可行/完整/风险/验收），可封驳退回中书省 |
| 尚书省 | `shangshu` | 拆解派发六部，汇总回奏 |
| 户/礼/兵/刑/工/吏部 | `hubu` `libu` `bingbu` `xingbu` `gongbu` `libu_hr` | 按职责执行 |
| 钦天监 | `qintianjian` | 数据分析、性能度量、趋势预测 |
| 早朝官 | `zaochao` | 每日采集新闻生成晨报 |

状态链（唯一事实源：`edict/backend/app/models/task.py`）：
`Taizi → Zhongshu → Menxia → Assigned → Doing → Review → PendingConfirm → Done`；
`Cancelled` 可从任意非终态取消；`Done/Cancelled` 为终态，不可覆盖、不可复活。
门下省封驳最多 3 轮，第 3 轮仍不通过则强制准奏（flow_log 记录「三封强准」）。

## 快速开始（Windows）

前置：Python 3.10+（无第三方依赖），可选 Node.js 18+（仅前端重建时需要）。

```powershell
# 1. 克隆并安装（无需 npm install / pip install）
git clone https://github.com/ppepperkok-hue/edict-codex.git
cd edict-codex

# 2. 启动看板服务（默认 http://127.0.0.1:7891，可 --port 指定）
python dashboard/server.py

# 3. 另开终端跑数据刷新循环（官员统计 + 实时数据 + 定时巡检）
powershell -ExecutionPolicy Bypass -File scripts/run_loop.ps1

# 4. 全量测试
python -m pytest tests/ -q
```

首次启动会自动生成 `data/agent_config.json`（从 `data/config.default.json` 模板）并创建启动快照。
浏览器打开 `http://127.0.0.1:7891` 即可使用军机处看板：旨意看板、省部调度、奏折阁、模板库、
官员总览、天下要闻、模型配置、技能管理、朝堂议政。

## 下旨方式

在 Codex 会话（本项目目录）里直接说正式旨意，太子按 `AGENTS.md` 编排协议建任务并 spawn 三省六部。
看板手动下旨或 `/api/agent-wake` 会把请求写入 `data/dispatch_queue.json`，太子在会话开始时与
每次任务收尾后轮询该队列并派发。

> **执行说明**：每个状态推进（create/state/done/delegate/confirm）都会自动把下一负责角色写入
> 派发队列，主会话消费队列后按角色派发。真实子 agent 派发为实验特性：当前 Codex 环境中
> spawn 的子 agent 可能不响应或行为失控（详见 DEV_PLAN ADR-015），不可用时由主会话代执行并记录。

CLI 示例（角色子 agent 使用；`--help` 可查全部命令）：

```powershell
python scripts/kanban_update.py create JJC-20260810-001 "任务标题" Zhongshu 中书省 中书令
python scripts/kanban_update.py state JJC-20260810-001 Menxia "方案已提交门下省审议"
python scripts/kanban_update.py flow JJC-20260810-001 "中书省" "门下省" "方案提交审议"
python scripts/kanban_update.py progress JJC-20260810-001 "正在执行" "步骤1✅|步骤2🔄"
python scripts/kanban_update.py todo JJC-20260810-001 1 "实现接口" completed
python scripts/kanban_update.py done JJC-20260810-001 "outputs/result" "执行完成摘要"
python scripts/kanban_update.py confirm JJC-20260810-001 approve "准予完结"
```

## 配置

- `data/config.default.json`：入库的默认配置模板；`data/agent_config.json` 为运行时配置（不入库），
  模型面板的改动写在这里，Codex 编排器 spawn 子 agent 时读取 model 字段作为模型覆盖参数。
- `skills/{role}/`：每个角色的技能目录，技能面板的增删改查与远程下载都落在项目内。
- 早朝新闻：`data/morning_brief_config.json` 的 `schedule` 控制每日采集时间（服务端内置定时线程，
  默认 08:00），结果写入 `data/morning_brief.json`。
- 密钥类配置一律走环境变量或 `.env`（已被 .gitignore 排除），不入库、不进备份。

## 回滚保障

```powershell
# 代码回滚（保留历史，可再撤销）
git revert v0.4.0..v0.5.0
# 临时切回某个里程碑
git checkout v0.4.0

# 数据快照与恢复（恢复前自动备份当前状态）
python scripts/backup_data.py
python scripts/restore_data.py --list
python scripts/restore_data.py --time "YYYY-MM-DD HH:MM:SS"

# 配置回滚：从默认模板重建运行时配置
python scripts/restore_data.py --reset-config
```

运行时 `data/*.json` 与备份不进 git；`data/schema.json`、`data/config.default.json` 入库作为模板。

## 前端重建（可选）

`dashboard/dist/` 已提交构建产物，开箱即用。若需改前端：

```powershell
cd edict/frontend
npm install
npm run build
# 将 edict/frontend/dist/ 产物复制到 dashboard/dist/ 后提交
```

## 目录结构（要点）

```text
AGENTS.md                 Codex 太子编排协议（本项目灵魂）
agents/<id>/SOUL.md       12 个角色模板
agents.json               角色与权限矩阵
dashboard/server.py       零依赖看板服务（API + 静态文件）
dashboard/dist/           前端构建产物（已提交）
scripts/                  看板 CLI / 备份恢复 / 技能管理 / 新闻采集
edict/backend/app/models/task.py  状态机唯一事实源
edict/frontend/           前端源码（React + Vite，可选重建）
data/                     运行时数据（不入库）+ config.default.json / schema.json
tests/                    pytest 全量测试
```

## License

MIT License，复刻自 [cft0808/edict](https://github.com/cft0808/edict)，保留原作者署名；
本仓库为独立新项目（`ppepperkok-hue/edict-codex`），非上游 fork。
