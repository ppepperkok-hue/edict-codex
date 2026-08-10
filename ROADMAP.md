# Edict-Codex · Roadmap

## v1（已完成，tag v0.1.0 → v0.5.0）

- 服务端：看板 SPA + HTTP API + 状态机 + 审计 + 官员统计 + 技能管理 + 早朝定时新闻 +
  朝堂议政 + 模型配置面板，零第三方依赖，本机 Windows 可跑。
- Codex 执行层：太子编排协议（AGENTS.md）+ 12 角色模板 + agents.json 权限矩阵，
  三省六部按需 spawn，看板经 CLI/API 更新。
- 工程保障：里程碑审查（都察院）、pytest 全量、代码 git tag/revert、数据快照备份/恢复、
  配置模板重置。

## 后续候选

- 御批模式：门下省审议结果呈送人工确认节点（看板审批面板）。
- 功过簿：各 agent 完成率、返工率、耗时统计与排行榜。
- 外部消息渠道：飞书 / Telegram 推送与接旨。
- 多机部署：Postgres + Redis 事件总线模式（上游 Phase 2，当前明确不做）。
- 前端源码与构建流程标准化（当前复用上游 dist 构建产物）。
