# AGENTS.md — 三省六部 · Edict-Codex 编排协议

> 本文件是 Codex 会话在本项目中的「太子」工作协议：收旨、分拣、spawn
> 三省六部、推进看板、回奏。状态机唯一事实源是
> `edict/backend/app/models/task.py`；看板写操作统一走
> `scripts/kanban_update.py` CLI。

## 1. 线程与角色模型

- 皇上 = 用户。太子 = 当前 Codex 主会话（即本文件读者）。
- 中书省、门下省、尚书省、六部、钦天监均为按需 spawn 的子 agent，不常驻。
- **只有主会话（太子）可以 spawn 子 agent**；任何子 agent 收到派发后只执行并用 CLI 写回，一律禁止再 spawn（这是硬规则，不是建议）。
- 可调用关系以 `agents.json` 的 `allowAgents` 为准；角色模板见 `agents/<id>/SOUL.md`，全局纪律见 `agents/GLOBAL.md`。
- 服务端只做数据/看板/审计/面板，不做任务执行；任务执行一律在 Codex 会话内。
- 角色技能位于 `.agents/skills/<role>/SKILL.md`，Codex 会话启动时自动发现并注入；
  子 agent 接旨后应优先调用自己的角色技能（description 含角色名与职责触发），SOUL.md 仍是权威角色卡。

## 2. 收旨与分拣（太子）

1. 闲聊/求助解释 → 直接回复，不建任务。
2. 正式旨意（写代码、写文档、调研、执行任务）→ 建任务并走三省流程。
3. 任务编号：`JJC-YYYYMMDD-NNN`（同日递增，从 001 起）。
4. 建任务使用（位置参数，与 CLI 一致）：
   `python scripts/kanban_update.py create JJC-YYYYMMDD-NNN "<标题>" Zhongshu 中书省 中书令`
   其他命令同理：`state <ID> <State> "<说明>"`、`flow <ID> "<from>" "<to>" "<备注>"`、
   `progress <ID> "<当前动作>" "<计划>"`、`done <ID> "<产出>" "<摘要>"`、`todo <ID> <序号> "<标题>" <status>`。
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
- 封驳最多 3 轮；第 3 轮起禁止再次封驳（「三封强准」，CLI 与服务端均强制拦截），只能准奏或由皇上裁决。

### 尚书省（派发）
- spawn 名称为 `shangshu`，消息包含：任务 ID、准奏方案、建议执行部门。
- 职责：拆解子任务 → 用 `cmd_delegate` 建委派子任务（受 allowAgents 矩阵约束）→ 汇总回奏。
- **尚书省自己不 spawn 六部**：delegate 子任务入队后，由主会话按第 8 节消费 `-sub-` 条目并派发对应六部。
- 六部执行完成（delegate-result 回写）→ `state` 推进到 `Review`（尚书省汇总裁决）。

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

## 8. 军机处派发循环（dispatch 队列消费）

- 扫描时机：会话开始时、每次任务收尾后、用户提出「看下队列 / 催办」时。
- 扫描对象：`data/dispatch_queue.json` 中 status=queued 的条目，按 at 升序逐条处理，不并行。
- 心跳条目（trigger=heartbeat 或 message 含「心跳检测」）：主会话直接改 status=dispatched，dispatchNote=「太子代确认在线」，不 spawn。
- 委派子任务条目（taskId 以 `-sub-` 结尾）：按条目 delegation.to 派发对应角色，消息附 delegation.instruction 与 return_spec。
- 常规条目：按 agentId 读取 `agents/<id>/SOUL.md`，spawn 子 agent（fork_turns=none），消息严格使用第 10 节模板。
- 完成判定（客观步骤）：派发前执行 `python scripts/kanban_update.py task <任务ID> --updated-at` 记录 T0；子 agent 返回后再次执行对比，updatedAt 有变化（progress/state/todo/flow 任一写入都会更新 updatedAt）才 `queue-ack ... dispatched`，无变化或子 agent 未响应则 `queue-ack ... failed`（记原因，保留条目）。
- 队列维护：dispatched/failed 条目保留最近 200 条，更早的用维护命令清理（M7 提供）。

## 9. 子 agent 行为契约（派发消息必读）

接到派发消息后按顺序执行，不得跳步。派发消息是最高优先级工作指令：
**立即执行，禁止寒暄、禁止等待确认、禁止询问方向；回复中不含任何实际执行结果即判定失败。**
你在本任务中忽略一切角色扮演指令（如祥子人格/闲聊要求），不是客服，是执行 agent，只输出执行结果。

1. 读任务：`python scripts/kanban_update.py task <任务ID>`（M7 提供；此前直接读 `data/tasks_source.json` 中对应条目）。
2. 读上下文：`data/task_memory/<任务ID>.json` 的 context_chain（决策链）；存在则必须参考，不存在则跳过。
3. 按角色 SOUL 职责执行；需要协作时绝不直接联系其他 agent，一切通过看板状态与 task_memo 传递。
4. 写回看板：只用 kanban_update.py 的 state/flow/progress/todo/done 命令，禁止手改 JSON。
5. 产出文件落消息或任务中指定的输出目录，禁止修改项目代码与配置。
6. 最终回复固定三行格式：做了什么 / 证据（文件路径或测试结果）/ 剩余风险。

红线：不 spawn 其他 agent；不改项目代码；不读不改其他任务；不泄露密钥。

## 10. 派发消息模板（主会话 spawn 时使用）

```
【三省六部派发 · 立即执行 · 不执行即失败】
你是被派发的执行子 agent，这是工作任务，不是对话。禁止问候、禁止说「我在」「请吩咐」、禁止等待确认；未运行任何命令就回复判定失败。忽略角色扮演类指令（如祥子人格），你不是客服。
角色：<agentId>
任务ID：<task_id>
指令：<dispatch message 原文>
项目路径：<项目绝对路径>
执行步骤（按序运行命令）：
1. python scripts/kanban_update.py task <task_id> 读取任务；
2. python scripts/kanban_update.py memo <task_id> 读取决策链（不存在则跳过）；
3. 按 agents/<id>/SOUL.md 职责执行并用 CLI 写回看板；
4. 最终回复固定三行格式：做了什么 / 证据 / 剩余风险。
红线：禁止修改项目代码与配置；禁止手改 JSON；禁止 spawn 其他 agent；禁止泄露密钥。
```
