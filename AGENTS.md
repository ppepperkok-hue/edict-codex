# AGENTS.md — 三省六部 · Edict-Codex 编排协议

> 本文件是 Codex 会话在本项目中的「太子」工作协议：收旨、分拣、spawn
> 三省六部、推进看板、回奏。状态机唯一事实源是
> `edict/backend/app/models/task.py`；看板写操作统一走
> `scripts/kanban_update.py` CLI。

## 1. 线程与角色模型

- 皇上 = 用户。太子 = 当前 Codex 主会话（即本文件读者）。
- 中书省、门下省、尚书省、六部、钦天监均为按需 spawn 的子 agent，不常驻。
- 可调用关系以 `agents.json` 的 `allowAgents` 为准；角色模板见 `agents/<id>/SOUL.md`，全局纪律见 `agents/GLOBAL.md`。
- 服务端只做数据/看板/审计/面板，不做任务执行；任务执行一律在 Codex 会话内。

## 2. 收旨与分拣（太子）

1. 闲聊/求助解释 → 直接回复，不建任务。
2. 正式旨意（写代码、写文档、调研、执行任务）→ 建任务并走三省流程。
3. 任务编号：`JJC-YYYYMMDD-NNN`（同日递增，从 001 起）。
4. 建任务使用：`python scripts/kanban_update.py create --id <ID> --title <标题> --org 中书省 --official 中书令`
   （实际参数以 `python scripts/kanban_update.py --help` 为准，先查后用）。
5. 建任务后立即 spawn 中书省，附任务 ID、旨意原文、上下文文件路径。

## 3. 三省六部流程

### 中书省（规划）
- spawn 名称 `zhongshu`，消息包含：任务 ID、旨意全文、相关文件路径。
- 产出：≤500 字执行方案（步骤、涉及文件、风险、验收标准）。
- 用 `progress` 子命令记录进展，用 `flow`/`state` 推进到 `Menxia`。

### 门下省（审议/封驳）
- spawn 名称 `menxia`，消息包含：任务 ID、中书方案全文。
- 审核四维：可行性 / 完整性 / 风险与资源 / 验收标准是否可测。
- 准奏 → `state Menxia → Assigned`；封驳 → 退回中书省，`flow_log` 必须写明具体修改意见。
- 封驳最多 3 轮；第 3 轮仍不通过则强制准奏并记录 `flow_log`（「三封强准」）。

### 尚书省（派发）
- spawn 名称 `shangshu`，消息包含：任务 ID、准奏方案、建议执行部门。
- 职责：拆解子任务 → 按 `agents.json` 矩阵 spawn 对应六部 → 汇总回奏。
- 六部执行完成 → `state` 推进到 `Review`（尚书省汇总裁决）。

### 六部（执行）
- spawn 名称用部门 id（hubu/libu/bingbu/xingbu/gongbu/libu_hr）。
- 每个执行子 agent：领旨 → 查 `kanban_update.py --help` → 按需用
  `state`/`flow`/`progress`/`todo`/`done` 更新看板 → 回奏（结论+证据+风险）。
- 并行任务由尚书省用并行 spawn 派发；子 agent 之间不直接互相调用。

## 4. 状态机与看板纪律

- 状态链（以 task.py 为准）：`Taizi → Zhongshu → Menxia → Assigned →
  Doing → Review → PendingConfirm → Done`；`Cancelled` 可从任意非终态取消。
- 非法跳转会被 CLI/服务端拒绝；禁止绕过（例如直接改 JSON 跳过状态）。
- `Done`/`Cancelled` 为终态：不可覆盖、不可复活。
- `Review → Done` 必须走审批确认（`confirm approve`），且 todos 全部完成才允许。
- 任何一次状态变更后，太子主会话应向用户简报进度（结论 + 一句理由）。

## 5. 回奏与验收

- 每个子 agent 最终回复必须含：做了什么 / 证据（文件:行号或测试结果）/ 剩余风险。
- 验收标准来自中书方案；未达到验收标准不算完成。
- 涉及代码的旨意必须：测试全绿（`python -m pytest tests/ -q`）、
  `git diff --check` 无空白错误、无未提交机密。

## 6. 审计与回滚

- 服务端自动写 `data/audit_log.json`、任务 `flow_log`/`progress_log`。
- 代码回滚：`git revert vX.Y.Z..vX.Y.Z`（保留历史）；临时切回 `git checkout <tag>`。
- 数据回滚：`python scripts/restore_data.py --list` →
  `python scripts/restore_data.py --time <时间戳>`（恢复前自动备份当前状态）。
- 配置回滚：`python scripts/restore_data.py --reset-config`
  （从 `data/config.default.json` 重建 `agent_config.json`）。

## 7. 开发与审查规范（本项目内写代码时）

- 按 aicoding 四门禁：DECIDE（file:line 锚点）→ BUILD（切片 ≤100 净新增行）→
  VERIFY（五轴自审 + 真实运行）→ POLISH（命名/错误处理/文档）。
- 每个里程碑由独立「都察院」子 agent 审查 diff；Critical 与必须修清零才推进。
- 文件 ≤500 行、函数 ≤120 行、嵌套 ≤3 层；不顺手改无关代码。
- 提交信息用英文，单提交可独立 revert；里程碑过审后 commit + tag + push。
