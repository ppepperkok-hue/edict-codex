# 角色技能接入（M11）审查报告（2026-08-11）

## 审查范围与方法

范围：本次变更全部内容 —— 12 份角色技能 `.agents/skills/{role}/SKILL.md`、
技能根目录从 `skills/` 迁移到 `.agents/skills/`（`dashboard/server.py` /
`scripts/skill_manager.py`）、角色技能登记到 `data/config.default.json`、
缺失的 `qintianjian` 角色补录、CLI 自动发现验证。

验证命令：

```powershell
python -m pytest tests/ -q
codex exec -C <项目根> -s danger-full-access --ephemeral -   # 暗号与角色触发探针
Invoke-RestMethod http://127.0.0.1:7891/api/skill-content/menxia/menxia
Invoke-RestMethod http://127.0.0.1:7891/api/agents-status
Invoke-RestMethod http://127.0.0.1:7891/api/remote-skills-list
```

## 总评

骨架健康：角色技能被 `codex exec`（v0.147.0）自动发现并注入，派发模拟中
子 agent 直接按门下省技能内容作答（四维审议/准奏封驳/必读命令），链路成立。
迁移过程发现并修复了一个真实 P1 缺陷（技能内容读取用 GBK 解码 UTF-8 中文
崩溃）和两个 P2 不一致（配置模板缺钦天监、面板按角色技能列表为空）。
当前 108 测试全绿，服务端 API 实测通过。剩余问题均为文档级或可接受的
已知边界，不影响使用。

## 问题清单

### P1（影响真实使用）

- **P1-1 已修复：技能内容读取编码崩溃**
  - 证据：`dashboard/server.py:306` 原为 `skill_path.read_text()`，Windows 默认 GBK
    解码 UTF-8 中文 SKILL.md 报 `'gbk' codec can't decode byte 0x81`；
    API 实测 `/api/skill-content/menxia/menxia` 返回 `ok=False`。
  - 影响：技能面板「查看内容」对任何含中文的 UTF-8 技能不可用。
  - 处置：改为 `read_text(encoding='utf-8')`；同一族问题一并修复——
    `scripts/skill_manager.py` 全部技能/源信息读写、`dashboard/server.py` 的技能模板
    写入/本地源读取/`.source.json` 读写/`agent_config.json` 写入全部显式
    `encoding='utf-8'`；新增回归测试
    `tests/test_cwe22_file_url.py:95 test_read_skill_content_utf8`，API 复测通过。

### P2（展示不一致 / 缺口）

- **P2-1 已修复：配置模板缺失钦天监**
  - 证据：`agents.json` 与 `dashboard/server.py:781` `_AGENT_DEPTS` 均为 12 角色，
    但 `data/config.default.json` 只有 11 个角色条目 + `main` 别名，无 `qintianjian`。
  - 影响：模型/技能面板无法配置钦天监。
  - 处置：`data/config.default.json:315` 补录 `qintianjian` 条目（含技能登记），
    运行时 `data/agent_config.json` 同步补齐。

- **P2-2 已修复：角色技能未登记到技能面板**
  - 证据：`dashboard/server.py:312 add_skill_to_agent` 只写文件不写
    `agent_config.json`；面板按角色读 `agent_config.json` 的 `skills[]`（原为空）。
  - 影响：技能文件存在但面板按角色技能列表看不到。
  - 处置：`data/config.default.json` 12 个角色（含 `main` 之外全部角色）登记
    `{name, path: .agents/skills/<role>/SKILL.md}`，运行时配置同步；API 实测
    `/api/agent-config` 返回 13 个 agent 且 12 角色均有 skills。

### P3（小问题 / 已知边界）

- **P3-1 已知：面板/CLI 添加的附加技能（嵌套结构）不会被 Codex 自动发现**
  - 证据：`dashboard/server.py:429 add_remote_skill` 写入
    `SKILLS_ROOT/<agent>/<skill>/SKILL.md`；Codex 只扫描
    `.agents/skills/<name>/SKILL.md` 一层。
  - 影响：面板管理的第三方技能仅对面板可见，子 agent 不会自动加载。
  - 处置：已在 `.agents/skills/README.md` 写明；如需自动发现，后续可改为
    平铺写入 `.agents/skills/<skill>/SKILL.md`（ADR 变更）。

- **P3-2 观察：远程技能列表天然跳过角色级 SKILL.md**
  - 证据：`dashboard/server.py:466-479` `get_remote_skills_list` 只收录含
    `.source.json` 的子目录，角色技能无源信息、按文件跳过，不误报。符合预期。

## 确认无问题的模块

- **Codex 项目级技能自动发现**：暗号探针（SKILL.md description 含「紫晶小马42」），
  `codex exec` 不运行任何命令直接回 `PROBE-OK` + 绝对路径；说明 `.agents/skills/`
  已注入系统上下文。
- **角色技能自动触发**：模拟「门下省派发」提示，CLI 子 agent 自动按 menxia 技能
  内容作答（四维审议、准奏/封驳、Review→Done 御批、先读任务与决策链）。
- **技能根目录切换**：`dashboard/server.py:58` 与 `scripts/skill_manager.py:32`
  均指向 `.agents/skills/`；模块导入实测输出路径正确。
- **官员/调度状态页**：`/api/agents-status` 返回 12 agents、configured=12
  （`_check_agent_workspace` 目录存在性判断成立）。
- **远程技能列表**：`/api/remote-skills-list` 返回 `count=0` 不崩溃。
- **测试基线**：`python -m pytest tests/ -q` → 108 passed in 11.05s。

## 验证记录

```text
python -m pytest tests/ -q
→ 108 passed in 11.05s

codex exec 暗号探针
→ PROBE-OK
→ C:\...\edict-codex\.agents\skills\probe\SKILL.md

codex exec 门下省派发模拟
→ 四维审议 / 准奏封驳 / 御批 / 先读任务与决策链（与 menxia SKILL.md 一致）

GET /api/live-status                       → ok, tasks=8
GET /api/skill-content/menxia/menxia       → ok=True, content 含「四维」
GET /api/agents-status                     → 12 agents, configured=12
GET /api/remote-skills-list                → ok=True, count=0
GET /api/agent-config                      → 13 agents, 12 角色各有 skills
```

## 后续建议

1. 如需面板添加的第三方技能也能被子 agent 自动调用，将写入路径改为平铺
   `.agents/skills/<skill>/SKILL.md` 并在 `add_remote_skill` 中强制技能名全局唯一。
2. ~~skill_manager 本地读写 UTF-8 隐患~~（已在本次处置，见 P1-1）。
3. 下次派发演练时把「角色技能自动调用」纳入验收项：派发消息不再附职责说明，
   仅给角色 id，验证子 agent 仍能按技能履行职责。
