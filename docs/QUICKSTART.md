# 三分钟上手 · Edict-Codex

## 方式一：直接在 Codex 会话里下旨（推荐）

在项目目录（本目录）打开 Codex 会话，直接说旨意，例如：

> 下旨：整理一份三分钟使用说明

Codex 主会话按 `AGENTS.md` 编排协议执行：太子分拣 → 中书规划 → 门下审议 →
尚书派发 → 六部执行 → 回奏，全程写看板。

## 方式二：启动看板服务

```powershell
python dashboard/server.py
```

浏览器打开 `http://127.0.0.1:7891`。可选数据刷新循环：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_loop.ps1
```

## 方式三：命令行手动操作

```powershell
python scripts/kanban_update.py create JJC-20260811-001 "任务标题" Zhongshu 中书省 中书令
python scripts/kanban_update.py state JJC-20260811-001 Menxia "方案提交门下省"
python scripts/kanban_update.py flow JJC-20260811-001 "中书省" "门下省" "方案提交审核"
python scripts/kanban_update.py progress JJC-20260811-001 "正在执行" "步骤1✅|步骤2🔄"
python scripts/kanban_update.py done JJC-20260811-001 "outputs/result" "执行完成摘要"
python scripts/kanban_update.py confirm JJC-20260811-001 approve "准奏"
```

状态链：`Taizi → Zhongshu → Menxia → Assigned → Doing → Review → PendingConfirm → Done`，
非法跳转会被拒绝；`Review→Done` 必须走御批确认。

## 回滚

```powershell
python scripts/restore_data.py --list
python scripts/restore_data.py --time latest
python scripts/restore_data.py --reset-config
git revert v0.4.0..v0.5.0
```

## 常见问题

- 看板打不开：确认 `python dashboard/server.py` 在运行，端口 7891 未被占用。
- 朝堂议政不可用：在 `data/llm_config.json` 配置 `{"api_key": "...", "base_url": "...", "model": "..."}`。
- 子任务未完成时 `done` 被拒：先 `todo ... completed` 全部完成。
- 中文乱码：确保终端用 UTF-8（`chcp 65001`）。
