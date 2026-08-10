# Edict-Codex 开发计划（DEV_PLAN）

> 复刻自 [cft0808/edict](https://github.com/cft0808/edict)（MIT License），面向 Codex 驱动运行。

## 项目概述

将原「三省六部」多 Agent 协作系统复刻为 Codex 驱动版：

- 独立服务端：看板（dashboard）、HTTP API、任务状态机、审计日志、技能管理、早朝新闻、朝堂议政，全部跑在本机 Windows，数据落 `data/*.json`。
- Codex 执行层：主 agent 按编排协议 spawn 子 agent（太子/中书省/门下省/尚书省/六部/钦天监），子 agent 通过 `scripts/kanban_update.py` CLI 或 HTTP API 更新看板。
- GitHub 同步：公开仓库 `ppepperkok-hue/edict-codex`，每个里程碑审查通过后 commit + tag + push。
- 回滚保障：代码走 git tag/revert；看板数据与配置走 `data/backups/` 快照 + 恢复脚本。

## 需求清单

### 核心流程（流程可靠性优先）

- 太子分拣：闲聊直接回复；正式旨意建任务（JJC-YYYYMMDD-NNN）并转中书省。
- 中书省规划：接旨 → 起草方案（≤500 字）→ 提交门下省审议。
- 门下省审议：可行性/完整性/风险/资源四维审核；封驳打回中书省，最多 3 轮，第 3 轮强制准奏。
- 尚书省派发：准奏后派发六部并行执行，汇总回奏。
- 状态机：非法跳转被拒；Done/Cancelled 终态不可覆盖；Review→Done 走御批确认。
- 审计：flow_log / progress_log / audit_log 完整可追溯。

### 完整功能

- 军机处看板：旨意看板、省部调度、奏折阁、旨库模板、官员总览、天下要闻、模型配置、技能配置、小任务会话、上朝仪式、朝堂议政。
- 模型配置面板：读写 `data/agent_config.json`，Codex 编排器 spawn 子 agent 时按配置应用模型。
- 技能管理：远程技能下载/更新/移除到 `skills/{role}/`。
- 早朝新闻：服务端每日定时采集 RSS 生成 `data/morning_brief.json`。

### 明确不做（v1）

- 外部消息渠道（飞书/Telegram/微信/webhook）——入口为 Codex 对话 + 看板 + HTTP API。
- Redis / Postgres / Outbox / Dispatch Worker / Gateway。
- OpenClaw 运行时与 openclaw.json 读写。

## 里程碑状态

| 里程碑 | 内容 | 状态 | Tag |
|---|---|---|---|
| M1 | 骨架与工程基座：源码搬运、git 仓库、pytest 基线 | 完成 | v0.1.0 |
| M2 | 服务端适配：配置路径、权限中间件、官员统计、备份/恢复 | 完成 | v0.2.0 |
| M3 | Codex 编排层：AGENTS.md 协议 + 12 角色模板 | 完成 | v0.3.0 |
| M4 | 完整功能接通：模型/技能/议政/早朝/模板/奏折 | 完成 | v0.4.0 |
| M5 | 交付验收：端到端演练、回滚演练、终审、文档收口 | 完成 | v0.5.0 |

## 决策记录（ADR）

- ADR-001：执行层采用 Codex 驱动（服务端不做通用任务 LLM 运行时），Codex 会话为主入口。
- ADR-002：服务端 API 增加 `X-Agent-ID` + `allowAgents` 权限中间件，写操作强制校验；CLI 保留文件锁。
- ADR-003：数据全部落 `data/*.json`，不引入数据库；运行时数据不入 git，`data/config.default.json` 作为配置模板入库。
- ADR-004：代码回滚用 git tag/revert；数据回滚用 `scripts/backup_data.py` / `scripts/restore_data.py`（保留最近 10 份快照）。
- ADR-005：保留 `edict/backend/app/models/task.py` 作为状态机单一事实源（kanban CLI 动态解析），其余 backend 代码不保留。
- ADR-006：前端直接复用原仓库 `dashboard/dist/` 构建产物并提交入库；`edict/frontend/` 源码保留供后续修改。
- ADR-007：废弃 OpenClaw 专属脚本（sync_from_openclaw_runtime / sync_agent_config / apply_model_changes / linucb_router / agentrec_advisor）与对应测试。
- ADR-008：废弃原测试 `test_sync_agent_config.py`、`test_sync_symlinks.py`（依赖已删脚本）；`test_e2e_kanban.py` 的 done 用例改为走完整状态机路径（Doing→Review→PendingConfirm→Done）。
- ADR-009：权限模型采用「无头=看板/CLI 特权，带头=按角色校验」；allowAgents 矩阵用于 agent-wake，任务写操作按任务归属校验（比矩阵更贴近执行模型）。
- ADR-010：看板手动下旨与 agent-wake 写入 `data/dispatch_queue.json`，Codex 主会话按 AGENTS.md 第 8 节轮询消费，形成「看板→Codex」闭环。

## 审查记录

每里程碑由独立「都察院」子 agent 审查，结论按 Critical / 必须修 / 可选分级，要求附 file:line 证据。

| 里程碑 | 审查日期 | 结论 | 处置 |
|---|---|---|---|
| M1 | 2026-08-10 | 通过（55 测试基线；e2e done 用例适配新状态机） | 已处置 |
| M2 | 2026-08-10 | 通过（权限/备份/统计新增测试；修复 create 参数与队列闭环） | 已处置 |
| M3 | 2026-08-10 | 通过（12 角色模板与 AGENTS.md 协议一致，无 OpenClaw 残留） | 已处置 |
| M4 | 2026-08-10 | 通过（议政配置源独立、早朝定时、旧前端清理；启动验证 + 权限 403 实测） | 已处置 |
| M5 | 2026-08-10 | 通过（CLI 全链路含封驳/御批/非法跳转；数据与代码回滚演练；81 测试全绿） | 已处置 |
| M4 | 2026-08-10 | 未单独留档，由 M5 终审覆盖复核 v0.4.0→v0.5.0 全部变更 | M5 终审覆盖 |

## 测试基线

```powershell
python -m pytest tests/ -v
```

当前基线：81 passed（M5 终版）。

## 回滚速查

```powershell
# 代码回滚到上一里程碑
git revert v0.1.0..v0.2.0
# 临时切回
git checkout v0.1.0

# 数据快照
python scripts/backup_data.py
python scripts/restore_data.py --list
python scripts/restore_data.py --time "YYYY-MM-DD HH:MM:SS"
```

## 遗留 TODO（M5 范围）

- [x] agents.json 改为 Codex 形态（12 角色 + allowAgents 矩阵，无 OpenClaw 路径）。
- [x] README/ROADMAP/CONTRIBUTING 收口；删除上游 OpenClaw 版 README_EN/JA/WINDOWS_INSTALL_CN。
- [x] CLI Windows GBK 控制台兼容（UTF-8 重配置 + --help）与回归测试。
- [x] skills/{role}/ 占位目录，官员总览显示 12 角色已配置。
- [x] M5 端到端演练（含门下封驳路径）。
- [x] M5 回滚演练（代码 revert / 数据 restore / 配置 reset）。
- [x] 都察院终审 v0.4.0→v0.5.0 diff，Critical/必须修清零。
- [ ] 终审通过后打 tag v0.5.0 并推送。

> 以下两条为 M4 完成时的旧记录，保留作历史参考：

- \gents.json\ 与 README 仍为上游 OpenClaw 形态，M5 收口时更新。
- M4 已完成：议政模块改为项目 \data/llm_config.json\ + EDICT_LLM_* 环境变量；删除旧版 \dashboard/dashboard.html\（服务端仅提供 React dist）；server 内置早朝定时线程（默认每日 08:00，读 morning_brief_config.json 的 schedule）。

## 回滚演练记录

- 数据回滚（2026-08-10）：`backup_data.py --label pre-drill` 建快照 → 写坏 `tasks_source.json` → `restore_data.py --path <snapshot>` 恢复为 `[]` 并触发刷新；`--reset-config` 从模板重建 `agent_config.json` 通过。
- 代码回滚（2026-08-10）：临时分支制造坏 commit → `git revert HEAD` → 坏文件删除、历史保留；分支已清理，main 不受影响。
- 改进：`restore_data.py --time latest` 现在跳过 before-restore/before-reset-config 安全快照，新增测试覆盖。
