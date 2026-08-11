# 项目级角色技能（Codex 自动发现）

本目录是 Edict-Codex 的项目级 skill 根目录。Codex（CLI `codex exec` 与桌面会话）会从
`<项目根>/.agents/skills/<name>/SKILL.md` 自动发现并注入技能，子 agent 接旨后可自动调用
对应角色的技能。

## 目录约定

- 每个角色一个目录，目录名 = agent id（与 `agents.json` 一致）：`zhongshu`、`menxia`、
  `shangshu`、`bingbu`、`gongbu`、`hubu`、`libu`、`libu_hr`、`xingbu`、
  `qintianjian`、`zaochao`、`taizi`。
- 每个技能必须包含 `SKILL.md`，frontmatter 至少含 `name` 与 `description`；
  description 写清触发场景（角色名 + 职责），让派发后的子 agent 自动选中自己的技能。
- 角色权威定义仍是 `agents/<role>/SOUL.md`；`SKILL.md` 给出执行契约并指向 SOUL.md，
  避免双份事实源漂移。
- 面板/CLI 添加的远程或本地附加技能沿用 `<agent>/<skill>/SKILL.md` 嵌套结构
  （面板按 agent 组织，不影响 Codex 对顶层角色技能的自动发现）。

## 管理入口

- 技能面板与服务端读写路径：`.agents/skills/`（`dashboard/server.py` 的 `SKILLS_ROOT`）。
- CLI 管理工具：`python scripts/skill_manager.py ...`（同样指向 `.agents/skills/`）。
- 运行时数据（`data/`）不入库；技能文件属于代码资产，随 git 提交与回滚。
