# 🔒 安全政策

## 支持的版本

| 版本 | 支持状态 |
|------|---------|
| main (latest) | ✅ 积极维护 |
| Docker `latest` | ✅ 积极维护 |
| 旧版本 | ❌ 不再维护 |

## 报告安全漏洞

**请勿通过公开的 GitHub Issue 报告安全漏洞。**

如果你发现了安全问题，请通过以下方式私密报告：

1. **首选方式**：使用 [GitHub Security Advisories](https://github.com/cft0808/edict/security/advisories/new) 创建私密安全报告
2. **备选方式**：发送邮件至维护者（请在 GitHub Profile 中获取联系方式）

### 报告应包含

- 漏洞类型（如：XSS、注入、权限绕过等）
- 受影响的文件路径和代码行
- 复现步骤
- 潜在影响评估
- 修复建议（如果有的话）

### 响应时间

| 阶段 | 时间 |
|------|------|
| 确认收到 | 48 小时内 |
| 初步评估 | 7 天内 |
| 修复发布 | 视严重程度，通常 30 天内 |

## 负责任披露

我们遵循负责任披露原则：

- 收到报告后会尽快确认并评估
- 修复完成前不会公开漏洞详情
- 修复发布后会在 Release Notes 中致谢报告者（除非报告者要求匿名）
- 我们不会对善意的安全研究者采取法律行动

## 安全最佳实践

如果你部署了三省六部系统，建议：

- 定期更新到最新版本
- 不要将 `data/` 目录暴露到公网
- 配置防火墙限制看板端口（默认 7891）的访问
- 使用反向代理（如 Nginx）时启用 HTTPS
- 为 LLM API Key 设置最小必要权限

## 看板写接口的信任边界

写接口（`POST /api/*`）按 fail-closed 处理，只接受以下来源：

- **同源请求**：浏览器 `Origin` 与本次请求的 `Host` 一致，且该 `Host` 必须是服务器的权威地址
  （实际 bind 地址 `--host`/`--port`，或 `--cors` 显式声明的 origin 的 authority）；
- **白名单来源**：`_DEFAULT_ORIGINS`（含 Vite dev `:5173`）或启动参数 `--cors <origin>` 指定的来源；
- **本地无 Origin 客户端**：`kanban_update.py`、`curl`、Codex 会话内的脚本（同机进程）；
- **携带有效 token 的客户端**：先 `POST /api/auth/setup` 设密码再用 `/api/auth/login` 取 token，
  以 `Authorization: Bearer <token>` 或 `edict_token` Cookie 提交。

`Host` 本身不被信任：DNS rebinding 页面会同时发出 `Origin` 与 `Host` 都为攻击者域名的请求，
所以仅比较两者相等会被绕过。权威 `Host` 集合由服务器的真实 socket 地址（`server_address`）、
loopback 别名与 `--cors`/内置 origin 的 authority 推导；`--host 0.0.0.0` 时额外接受任意
IP 字面量（IP 不受攻击者 DNS 控制），但域名仍被拒绝。`X-Forwarded-Host` 一律不参与判定
（客户端可伪造，仓库也没有可信代理配置）。

带 `Origin` 的写请求中，以下情形一律拒绝：`Host` 不是权威地址（含 `Host` 缺失或重复）、
`Origin` 不在白名单且与权威 `Host` 不同源、`Sec-Fetch-Site: cross-site`、
`Origin: null`（沙箱 iframe / `file://` 页面）、以及非 `application/json` 的请求体
（`text/plain`、`application/x-www-form-urlencoded`、`multipart/form-data`）。

`Sec-Fetch-Site: same-site` 只在 `Origin` 命中白名单（Vite `:5173` 或 `--cors`）时放行：
loopback 等站点的「site」忽略端口，所以 `127.0.0.1:5173` 的 Vite 页面写 `127.0.0.1:7891` 时
浏览器报的就是 `same-site`，这一对是文档化的合法组合。`same-site` 本身不产生信任：
白名单之外的同站来源（例如同机另一个端口的页面）仍被拒绝，且 `Sec-Fetch-Site: cross-site`
即使 `Origin` 在白名单中也拒绝。

反向代理部署时需显式 `--cors https://你的域名`，并让代理保留原始 `Host`（常见默认行为）；
代理若把 `Host` 改写成上游地址（如 `127.0.0.1:7891`）同样可用，因为那就是权威 bind 地址。
两种情况下都不要依赖 `X-Forwarded-Host`。

残余风险：`X-Agent-ID` 是未认证的声明，只能缩小权限、不能证明身份；同机进程仍可直接读写
`data/*.json`。需要更强的 agent 身份认证时，应引入独立的每 agent 凭据（当前仓库没有该凭据来源）。

## 致谢

我们感谢所有帮助提升三省六部系统安全性的安全研究者。
