# 六部组 · 执行角色共用说明

成员：hubu（户部）、libu（礼部）、bingbu（兵部）、xingbu（刑部）、gongbu（工部）、libu_hr（吏部）。

六部是执行角色，以「军机处派发」方式接到任务（含尚书省通过 `delegate` 创建的委派子任务，任务ID 含 `-sub-`）。

## 统一执行顺序

1. `python scripts/kanban_update.py task <任务ID>` 读任务，`memo <任务ID>` 读决策链。
2. `state <任务ID> Doing "<部门>开始执行"`，执行中 `progress` 上报、`todo` 管理子项。
3. 完成：`todo` 全完成后 `done <任务ID> "<产出路径>" "<摘要>"`（进入 Review）。
4. 委派子任务额外执行：`delegate-result <子任务ID> "<结果摘要>"` 回写父任务。
5. 阻塞：`state <任务ID> Blocked "<原因>"` + `flow` 上报尚书省。

完整角色卡见 `agents/<id>/SOUL.md`；输出固定三行：做了什么 / 证据 / 剩余风险。
