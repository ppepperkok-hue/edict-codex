# Edict-Codex 审查报告（2026-08-11）

## 审查范围与方法

- 范围：后端（`dashboard/server.py`、`scripts/kanban_update.py`、`edict/backend/app/models/task.py`、`scripts/*`）、前端（`edict/frontend/src` 源码与 `dashboard/dist` 构建产物）、API 端点、数据链路、配置与文档一致性。
- 方法：与原项目（cft0808/edict，工作副本 `work/edict-full`）逐文件/逐函数对照；前端端点与后端路由交叉检查（脚本 `work/cross_check_api.py`）；API 实跑字段抽查；组件状态三态抽查；端到端数据链路实跑；硬编码一致性核对；`pytest` 全量。
- 验证命令：`python -m pytest tests/ -q`；`python dashboard/server.py` + `curl /api/*`；`python scripts/kanban_update.py create/state/todo/done/confirm` 全链路；`git diff --no-index` 对照原版。

## 总评

骨架与原项目对齐度高：状态机、CLI 命令集、数据清洗、文件锁、调度器、前端构建产物均与上游一致或仅按计划收紧；API 端点原版全保留并只增不减；权限矩阵在 CLI 委派层落地（比原版文档承诺更硬）。主要风险集中在执行层：真实子 agent 派发在当前 Codex 环境不可用（已记录 ADR-015），派发消息与「完成判定」协议未工具化，文档存在少量与代码不一致的承诺（三封强准、都察院审查）。未发现 P0 级数据损坏或无法运行问题。

## 问题清单

### P1（影响真实使用）

1. 子 agent 派发不可用，核心多 agent 路径无法真跑。
   - 证据：`docs/DEV_PLAN.md` ADR-015（fork_turns=none 5/5 次仅寒暄不执行；fork_turns=all 递归 spawn 并篡改看板数据）。
   - 影响：门下独立审议、六部并行执行只能由主会话代执行，四眼原则打折。
   - 建议：保持主会话代执行兜底；将协议第 10 节消息模板与子 agent 实验状态写入 README 使用说明；环境升级后重测。

2. AGENTS.md 第 8 节「完成判定」未工具化。
   - 证据：`AGENTS.md` 第 8 节（「子 agent 返回且看板状态有推进…标记 dispatched」）与 `scripts/kanban_update.py` 的 `cmd_queue_ack`（约 1036 行）之间缺少「判定是否有推进」的客观步骤。
   - 影响：主会话凭感觉判定，可能误标 dispatched/failed。
   - 建议：协议明确「派发前 `task <ID>` 记录 updatedAt，返回后对比，有变化才 dispatched」，或将对比逻辑做成 CLI 子命令。

3. 派发消息从原版分角色定制降级为通用模板。
   - 证据：原版 `dashboard/server.py` `dispatch_for_state` 内 `_msgs` 为 taizi/zhongshu/menxia/shangshu 各写操作指引；我们的 `scripts/kanban_update.py` `_enqueue_next_dispatch`（约 1056 行）只发「状态为 X，请按职责处理」。
   - 影响：子 agent 接单时缺少「请勿重复创建」「请立即转交中书省」等引导。
   - 建议：恢复四角色定制文案（至少对齐原版措辞）。

### P2（展示错误 / 不一致 / 死模块）

4. 「三封强准」仅文档承诺，代码无强制。
   - 证据：`AGENTS.md` 第 3 节（「封驳最多 3 轮；第 3 轮仍不通过则强制准奏」）；`dashboard/server.py` `handle_review_action`（约 748 行）只递增 `review_round`，第 3 轮仍可继续封驳。原版代码同样无强制逻辑。
   - 影响：文档与行为不一致；子 agent 不可用时无人执行「强准」。
   - 建议：二选一——在 `handle_review_action` 实现第 3 轮强制准奏，或改文档为「第 3 轮应由皇上/主会话裁决」。

5. 死代码：`get_agent_activity_by_keywords` 无调用点。
   - 证据：`dashboard/server.py:1589` 仅定义，全仓无调用（M9 移除 session 融合后遗留）。
   - 建议：删除；其内部调用的 `get_agent_activity` 仍被 `/api/agent-activity` 使用，保留。

6. `test_e2e_kanban.py` 使用真实 `data/` 目录运行测试。
   - 证据：`tests/test_e2e_kanban.py` 的 `TASKS_FILE` 指向项目 `data/tasks_source.json`（fixture 虽备份恢复，但曾出现 PermissionError 偶发）。
   - 影响：测试与真实运行环境竞争文件，可能偶发失败。
   - 建议：`TASKS_FILE` 也重定向到临时目录（与队列隔离一致）。

7. 文档与现状不一致。
   - 证据：`DEV_PLAN.md` 第 7 节「每个里程碑由独立都察院子 agent 审查」与 ADR-015（子 agent 不可用）矛盾；README「下旨方式」已加注但 DEV_PLAN 未同步。
   - 建议：DEV_PLAN 改为「自审 + 五轴」，标注子 agent 审查为实验性。

### P3（小问题 / 体验）

8. 前端数据面板普遍缺 loading 态。
   - 证据：`edict/frontend/src/components/EdictBoard.tsx`、`MorningPanel.tsx` 有空态（「暂无旨意」「暂无数据」）与错误 toast，但无加载骨架。
   - 建议：核心面板补 loading 占位（低优先级）。

9. server 路径派发入队无去重。
   - 证据：`dashboard/server.py` `_enqueue_dispatch`（约 800 行）直接 append；CLI 路径 `_enqueue_next_dispatch` 已有去重。
   - 影响：调度器重试可能重复入队同 agent 条目（原版同样行为）。
   - 建议：`_enqueue_dispatch` 对齐 CLI 去重逻辑。

## 确认无问题的模块

- 状态机：`edict/backend/app/models/task.py` 与原版唯一差异为 Doing→Done 直通被收紧（流程可靠性决策），`tests/test_state_machine_consistency.py` 覆盖两侧一致性。
- CLI 命令集：原版 17 个命令全部保留，新增 6 个（task/memo/memory-view/queue-purge/queue-ack），`AGENT_POLICY` 只增不减。
- 数据清洗与并发：`_sanitize_*`、`file_lock.py` 与原版零差异；委派有深度/循环/权限矩阵三重防护。
- 前端：`dashboard/dist` 与原版 SHA256 一致；前端 33 个 API 端点全部在后端有路由实现（脚本交叉检查全 OK）；MorningPanel/EdictBoard/SkillsConfig 有空态与错误 toast。
- API 字段：实跑 `/api/live-status`、`/api/agent-config`、`/api/officials-stats` 字段齐全；`/api/morning-brief` 空对象时前端有可选链防护。
- 调度器：与原版一致，另含两处修复（updatedAt 兜底、有 queued 派发的任务跳过扫描）；阈值默认 600 秒与 API 传参 180 秒的覆盖关系与原版一致。
- 备份/恢复/回滚：M5 演练过数据恢复与代码 revert，`restore_data.py` 的 latest 选择已跳过安全快照。
- 硬编码一致性：MAX_PROGRESS_LOG=100、MAX_AUDIT_LOG=5000、MAX_DELEGATION_DEPTH=3、队列 cap 200 在 CLI 与 server 两侧一致。

## 验证记录

- `python -m pytest tests/ -q` → 101 passed（10.41s）。
- 端到端实跑（`JJC-REVIEW-001`，已清理）：create → Menxia → Assigned → Doing → todo completed → done(Review) → PendingConfirm → confirm approve → Done，每个状态推进自动入队（zhongshu/menxia/shangshu 依次 queued），终态 Done 可查。
- API 抽查：`/api/live-status` 顶层 8 键、`officials[0]` 25 键；`/api/agent-config` 5 键；`/api/officials-stats` 4 键；`/api/morning-brief` 空对象（前端可选链防护）。
- 端点交叉检查：`edict/frontend/src/api.ts` 33 个端点全部命中后端路由（OK），后端共 47 条路由。
- 前端构建：未执行（`edict/frontend` 无 node_modules，package.json 无 test 脚本）；`dashboard/dist` 与上游哈希一致，作为构建等价证据。
- 原版对照：kanban_update.py +257/-20（只增逻辑），server.py +360/-563（删除项均为 OpenClaw 专属或 session 融合残留，已逐一核对），task.py 1 行收紧。

## 后续建议

- 修复优先级：P1-2（完成判定工具化）→ P1-3（恢复角色化派发消息）→ P2-4（三封强准二选一）→ P2-5/6/7（死代码、测试隔离、文档同步）→ P3。
- 需要补的测试：完成判定对比逻辑（如做成 CLI 子命令）、三封强准（若实现）、server 入队去重。
- 需要删除的死模块：`get_agent_activity_by_keywords`。
