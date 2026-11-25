# S5-INTEL-027 · 情报条目主管审批流与状态流转规则

会员空间平台「情报简报」模块的审批后端：员工核对提交 → 主管审批（四眼原则 + 原文链接复检）→
编入简报发布；驳回带意见回到核对，approved 后内容锁定，任一状态可过期下线。

- 技术栈：Python 3.11+ / FastAPI / SQLAlchemy 2 / Alembic / PostgreSQL 16
- 数据：全部为虚构 UUID、虚构标题/摘要与 `example.invalid` 链接；不含真实个人信息、企业信息，不出现客户名称
- 外部数据工具：**未调用** `tool_hints` 中的 CompanyEnrich 等目录服务（本单不需要企业信息补全，且与「只用虚构数据」约束冲突）
- 状态机唯一口径：[`docs/state-machine.md`](docs/state-machine.md)（含 Mermaid 流转图与副作用流程图）

## 1. 目录

```text
app/
  config.py                  # DATABASE_URL / APP_TIMEZONE / LINK_RECHECK_TIMEOUT_SECONDS / REMINDER_SERVICE_URL（仅环境变量）
  db.py                      # engine 与 session
  principal.py               # 调用者身份值对象（org/site/user/role）
  enums.py                   # 状态、相关性、审批动作、提醒状态、角色
  state_machine.py           # TRANSITIONS 表：状态机唯一事实源
  schemas.py                 # Pydantic 请求/响应（驳回意见必填在此层 422）
  models/                    # intel_items / intel_approvals / intel_audit_logs /
                             # intel_briefing_candidates / intel_reminder_outbox
  services/
    approvals.py             # 审批与全部生命周期动作（事务边界在此）
    link_checker.py          # 原文链接复检：HttpLinkChecker（stdlib）+ StubLinkChecker
    matcher.py               # 会员企业匹配桩（确定性虚构 UUID）
    reminder.py              # 提醒服务桩 + 派发结果
    briefing.py              # 本周简报候选（周一为 week_start）
    errors.py                # 领域错误 → HTTP 状态码
  api/deps.py                # S2-IAM 请求头桩 + 三个可注入服务（生产替换点）
  api/intel.py               # 路由
  jobs/retry_reminders.py    # 失败提醒重试 CLI
migrations/versions/0001_intel_approval_flow.py
scripts/                     # 虚构数据种子、测试与迁移检查入口
tests/                       # 4 条 AC + 全矩阵/权限/副作用/约束/迁移测试
docs/state-machine.md        # 状态流转图与规则口径
evidence/                    # 本轮可复现记录
```

## 2. 快速开始

### 2.1 起一个测试 PostgreSQL 16

```bash
docker compose -f docker-compose.test.yml up -d
# 端口 127.0.0.1:55427，库名 intel_approval_test，trust 认证（仅测试用）
```

或使用已有 PostgreSQL 16，库名建议包含 `test`（pytest 会校验）。

### 2.2 安装与迁移

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

export DATABASE_URL="postgresql+psycopg://tester@127.0.0.1:55427/intel_approval_test"
export APP_TIMEZONE="Asia/Shanghai"

.venv/bin/alembic upgrade head
```

生产环境把用户名/密码/主机换成对应值，连接串只从环境变量读取。

### 2.3 生成虚构条目并启动 API

```bash
.venv/bin/python scripts/seed_fictional_items.py --seed 42
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
# OpenAPI: http://127.0.0.1:8000/docs
```

种子脚本只清理并写入自己的虚构 org，可重复执行。

## 3. 接口

### 3.1 身份请求头（S2-IAM 桩，见 §7）

| 头 | 说明 |
|---|---|
| `X-Org-Id` | 必填；缺失 401，非法 UUID 400 |
| `X-User-Id` | 写操作必填（四眼原则与审计需要真实 actor）；缺失 401 |
| `X-User-Role` | `supervisor` / `staff`；缺省 `staff`（最小权限）；其他值 400 |
| `X-Site-Ids` | 可选，逗号分隔；缺省=该 org 全部站点 |

### 3.2 端点

| 端点 | 角色 | 说明 |
|---|---|---|
| `GET /api/intel/approvals?status=pending` | 主管 | 待审批列表（=checked）；`status` 还可取 `approved` / `rejected`（最近决定为驳回且正在返工）/ `expired`；`limit` 1–100 默认 20，`offset` |
| `GET /api/intel/items/{id}` | 任意 | 条目详情（含最近驳回意见 `review_comment`） |
| `PATCH /api/intel/items/{id}` | 任意 | 编辑 title/summary/match_conditions/relevance；approved/published/expired → 409 |
| `POST /api/intel/items/{id}/submit` | 任意 | 员工提交核对结果：in_check → checked |
| `POST /api/intel/items/{id}/approve` | 主管 | checked → approved；四眼 403、复检失败 409；可选 body `{"comment": "..."}` |
| `POST /api/intel/items/{id}/reject` | 主管 | checked → in_check；body `{"comment": "..."}` 必填（缺失/空白 422） |
| `POST /api/intel/items/{id}/withdraw` | 主管 | approved/published → in_check，解锁内容 |
| `POST /api/intel/items/{id}/publish` | 主管 | approved → published |
| `POST /api/intel/items/{id}/expire` | 主管 | 任一非终态 → expired |

错误体统一为 `{"detail": "...", "code": "...", "extra": {...}?}`；
`code ∈ illegal_transition(409), four_eyes_violation(403), link_recheck_failed(409),
content_locked(409), forbidden_role(403), not_found(404), missing_actor(401),
reject_comment_required(422)`。参数校验错误为 FastAPI 标准 422。

### 3.3 示例

```bash
ORG=a0000000-0000-4000-8000-000000000001
SUP=00000000-0000-4000-8000-000000000052   # 与核对人不同的主管
ITEM=<条目 UUID>

# 待审批列表
curl -sS -H "X-Org-Id: $ORG" -H "X-User-Id: $SUP" -H "X-User-Role: supervisor" \
  "http://127.0.0.1:8000/api/intel/approvals?status=pending"

# 通过（自动复检原文链接；high_relevance 匹配会生成当日提醒）
curl -sS -X POST -H "X-Org-Id: $ORG" -H "X-User-Id: $SUP" -H "X-User-Role: supervisor" \
  "http://127.0.0.1:8000/api/intel/items/$ITEM/approve"

# 驳回（意见必填）
curl -sS -X POST -H "X-Org-Id: $ORG" -H "X-User-Id: $SUP" -H "X-User-Role: supervisor" \
  -H "Content-Type: application/json" -d '{"comment":"请补充原文佐证"}' \
  "http://127.0.0.1:8000/api/intel/items/$ITEM/reject"
```

approve 响应包含 `item`、`approval`（决定记录）、`briefing_week_start`（本周周一）与
`reminder`（`{outbox_id, status}`，非 high_relevance 时为 null）。

## 4. 规则与设计判断

工单规则逐条落位：

1. **审批前自动原文链接复检**：`approve` 内置调用 `LinkChecker.check(source_url)`，失败 409 且条目保持 checked，写 `approve_blocked` 审计。生产实现只用 stdlib urllib 请求条目自己的链接（HEAD，405/501 时 GET 回退），无第三方 SDK。
2. **四眼原则**：`approver == checked_by` → 403。`checked_by` 在 submit 时记录；DB CHECK 保证 checked 条目必有核对人。
3. **approved 后摘要与条件锁定**：PATCH summary/match_conditions 在 approved/published → 409；修改须先 withdraw 回 in_check。
4. **每次审批写 intel_approvals 与审计日志**：approve/reject/withdraw 各写一条决定记录 + 一条审计；submit/publish/expire/update/reminder_dispatch 写审计。
5. **通过后两件事**：加入本周简报候选（同事务）；high_relevance 且匹配到会员企业时生成当日提醒 outbox（同事务），提交后派发。
6. **仅主管可审批**：approve/reject/withdraw/publish/expire 与审批列表均要求 supervisor。

显式声明的设计判断（规格未细说处的保守选择）：

- **四眼只约束 approve**：主管驳回自己核对的条目是 harmless 的退回动作，允许（有测试）。
- **锁定批次扩展到 title/relevance**：与摘要/条件同批锁定，避免已审批内容被旁路修改；expired 终态不可编辑。
- **checked 状态下编辑内容自动回落 in_check**：内容变了就必须重新核对提交，防止「提交后偷改」绕过审批。
- **守卫顺序**：角色 → 数据范围 → 状态(409) → 四眼(403) → 复检(409)，保证 AC-1 的 409 语义稳定、四眼拦截不消耗复检。
- **撤回/过期的清理**：软删该条目全部在库简报候选、把 pending 提醒置 skipped；已 sent 的提醒不追溯。
- **并发**：写路径对条目行 `SELECT … FOR UPDATE`，重复 approve 第二次稳定 409（有测试）。

## 5. 数据模型

五张表全部含统一字段 `id(UUID)/org_id/site_id/created_at/created_by/updated_at/deleted_at`（软删除）。

| 表 | 关键列 | 关键约束 |
|---|---|---|
| `intel_items` | title, summary, source_url, relevance, match_conditions(JSONB), status, checked_by/at, approved_by/at, published_at, expired_at, review_comment | status/relevance 枚举 CHECK；checked⇒checked_by 非空；approved/published⇒approved_at 非空 |
| `intel_approvals` | item_id(FK), action(approve/reject/withdraw), from_status, to_status, comment, decided_by, link_recheck_ok, link_recheck_detail | reject⇒comment 非空且非空白（DB CHECK） |
| `intel_audit_logs` | entity_type, entity_id, action, actor_id, detail(JSONB) | (org_id, entity_id, created_at) 索引 |
| `intel_briefing_candidates` | item_id(FK), week_start(周一) | 部分唯一 (org_id,item_id,week_start) WHERE deleted_at IS NULL |
| `intel_reminder_outbox` | item_id(FK), remind_on, payload(JSONB), status(pending/sent/failed/skipped), attempts, last_error, dispatched_at | status 枚举 CHECK |

`review_comment` 保存最近一次驳回意见（返工时始终可见）；完整决定历史在 `intel_approvals`。
FK 一律 `ON DELETE RESTRICT`，与软删除哲学一致。

## 6. 测试

```bash
export TEST_DATABASE_URL="postgresql+psycopg://tester@127.0.0.1:55427/intel_approval_test"
.venv/bin/pytest -q
# 或：scripts/test.sh
```

安全护栏：`tests/conftest.py` 拒绝数据库名不含 `test` 的连接串；每个用例前 TRUNCATE 五张表；
链接复检/匹配/提醒全部注入桩，**测试套件不产生任何网络请求**。

本轮实测（PostgreSQL 16 / Python 3.12）：

```text
111 passed
alembic check: No new upgrade operations detected.
```

| 文件 | 覆盖 |
|---|---|
| `test_ac1_approve_in_check_409.py` | **AC-1**：in_check 直接 approve → 409；重复 approve 第二次 409 |
| `test_ac2_four_eyes_403.py` | **AC-2**：主管审批自己核对的条目 → 403；另一主管可通过；四眼先于复检 |
| `test_ac3_reject_comment.py` | **AC-3**：无/空/空白意见 → 422；驳回回 in_check 且意见保留（含重提后） |
| `test_ac4_locked_after_approved.py` | **AC-4**：approved/published/expired 改摘要/条件 → 409；撤回后可编辑 |
| `test_state_machine_matrix.py` | 6 动作 × 5 状态全矩阵；API 行为与 TRANSITIONS 表一致；expired 终态 |
| `test_link_recheck.py` | 复检失败拦截 + 审计；成功记录在决定上；非法状态不消耗复检 |
| `test_permissions.py` | 主管专属动作、actor 必填、org/site 隔离、软删 404、非法头 |
| `test_approval_side_effects.py` | 决定+审计+本周候选；high_relevance 提醒；无匹配 skipped；提醒故障不回滚审批；重试；候选幂等 |
| `test_withdraw.py` | 撤回清时间戳/候选/提醒；published 撤回；撤回后重新走全流程 |
| `test_approvals_list.py` | pending/approved/rejected/expired 过滤、分页、site 范围 |
| `test_constraints.py` | DB 层枚举、驳回意见、唯一候选、FK RESTRICT |
| `test_migration_roundtrip.py` | upgrade → downgrade -1 → upgrade；`alembic check` 零漂移 |

## 7. 对接点（桩先行，生产替换清单）

| 对接点 | 当前实现 | 生产替换 |
|---|---|---|
| **S2-IAM**（身份/角色/数据范围） | `app/api/deps.py::get_principal` 读 `X-Org-Id/X-User-Id/X-User-Role/X-Site-Ids` | 校验 Bearer token → 查 org 成员关系、可见 site、角色 → 返回同样的 `Principal`；服务层/路由零改动。**请求头桩仅限本工单隔离演示与测试，不得用于生产认证授权** |
| **原文链接复检** | `HttpLinkChecker`（stdlib urllib，仅请求条目自身 source_url）；测试注入 `StubLinkChecker` | 如需经采集侧代理复检，替换 `get_link_checker` 返回的实现即可 |
| **会员企业匹配** | `StubMemberMatcher`：由 match_conditions 派生确定性虚构 UUID（空条件=无匹配） | 对接会员 CRM 匹配工单，替换 `get_matcher` |
| **提醒服务** | `StubReminderService`：记录调用、可模拟故障；outbox 持久化 | HTTP 客户端调提醒工单（`REMINDER_SERVICE_URL`），替换 `get_reminder`；outbox 契约不变 |
| **条目录入/规范化** | `intel_items` 由本单迁移定义**最小契约**（审批流所需列）；录入/去重属兄弟工单 | 核心团队集成时与兄弟工单 schema 合并；`source_id`/`raw_page_id` 为指向 S5-INTEL-001 表的松 UUID 引用（无跨交付外键） |
| **简报编制/发布** | 本单维护 `intel_briefing_candidates` 候选池并提供 publish 状态位 | 简报工单按 `(org_id, week_start)` 消费候选池 |

## 8. 配置与保密

| 环境变量 | 必填 | 说明 |
|---|---|---|
| `DATABASE_URL` | 是 | `postgresql+psycopg://...`，只从环境读取 |
| `APP_TIMEZONE` | 否 | 默认 `Asia/Shanghai`；决定 week_start 与 remind_on 的归属日 |
| `LINK_RECHECK_TIMEOUT_SECONDS` | 否 | 默认 5；生产复检超时 |
| `REMINDER_SERVICE_URL` | 否 | 提醒工单地址（对接点；桩不使用） |

仓库不含真实密钥、连接串或客户名称；不引入向境外发送数据的第三方 SDK；
`tool_hints` 外部目录工具未调用。

## 9. 已知边界与排除项

- 不实现 S2-IAM 本体、条目录入/抓取/去重、简报排版与推送渠道、前端工作台；
- 过期下线提供手动端点；定时批量过期属调度工单，可直接复用 `expire_item`；
- 提醒重试为手动 CLI（`python -m app.jobs.retry_reminders`），常驻重试调度可按需挂 cron；
- `rejected` 列表口径 = 最近一次决定为驳回**且**当前在 in_check 返工；已重提的条目回到 pending；
- 匹配桩的「1–3 个虚构企业」仅为演示语义，真实匹配规则以 CRM 工单为准。

## 10. 证据

`evidence/` 保留本轮可复现记录：迁移往返与 `alembic check`（`migration-check.txt`）、
pytest 全量输出（`test-results.txt`）、虚构数据种子输出（`seed.log`）、
接口样例响应（`api-samples.json`，含 409/403/422 错误体与生产复检失败样例）。

样例可用 `scripts/demo_api_samples.py` 复现：先起服务
（`uvicorn app.main:app --port 8027`），再运行该脚本；成功路径的复检目标指向服务自身的
`/openapi.json`，全程不依赖外部网络目标。

## 11. 模板来源声明

按工作区规范显式复制并声明：`app/models/base.py` 的统一字段 mixin 布局复制自兄弟工单
S5-INTEL-001；`app/config.py`、`app/db.py`、`app/api/deps.py` 的请求头桩模式、
`migrations/env.py`、测试护栏（conftest 的 test 库名校验）沿用 S5-EVAL-039 的既有范式。
两个交付仓库相互独立，无跨任务 import。