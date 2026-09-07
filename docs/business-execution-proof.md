# 后台业务执行独立黑盒验收

## 范围与结论

本轮验证的是**后台确实传递并使用采集证据决定策略和稿件**，不是 UI 自动点击，也不是真实商业模型智能、真实外站发布或 GEO 增长证明。验收客户端只通过 HTTP 操作真实 uvicorn/FastAPI；没有导入 executor 手动调用函数，没有启动浏览器或新 Next 实例。

隔离后端 `127.0.0.1:8004`，受控 OpenAI-compatible / WordPress / Razormind 协议 peer `127.0.0.1:18774`。每个场景使用独立临时 SQLite 和全新 peer；B 开始前恢复原官网正文是明确 fixture 准备。正式 `geo.db` 未用于创建验收项目。受控 peer 不是生产模型或平台，没有真实账号、付费调用或真实外站写入。

验收人允许的后台写动作只有：建项目、一次登记 source/publisher、提交相同 goal、批准 plan、批准精确稿件并授权发布。官网抓取、collect/sync/analyze、策略、生成、WP 提交、公开 GET 核验与 retest 均由持久后台执行；HTTP GET 仅观察状态。

## 旧问题：独立实测复现

在源修复导入前启动无 reload 的旧进程：

- 模型 HTTP 顺序为 discovery → plan → draft。
- `draft_model` 开始于 **2026-09-05 18:12:48.185445 UTC**；待审稿已经存在时采集任务数为 **0**。
- 第三次模型请求只有 `instructions / before_text / facts`，没有 AI 回答或证据策略。
- 批准发布之后才开始 `baseline:collect`，时间 **18:12:56.718460 UTC**。
- 后续虽然 completed、2 次 collect、1 次 WP POST，但基线不可能参与此前稿件决策。

短证据：`artifacts/business-proof/old-ordering-summary.json`；请求与阶段证据：`old-ordering.json`。不是根据源码猜测的旧输出。

## 新链：证据差分验收

后台修复文件由业务逻辑 owner 交付：`backend/app/agent_runtime.py`、`backend/app/agent_schemas.py`、新增 `backend/app/agent_evidence.py`；协议 fixture 为 `tests/agent_peer.py`。没有数据库 schema 变更。

新阶段是 materialize → baseline collect/sync/analyze → evidence freeze → strategy_model → draft → 人审 → WP POST → 公开 GET verify → retest。context 同时冻结已有同项目回答、固定分析/问题版本及符合条件研究；本次独立 A/B 使用新采基线，未冒称独立覆盖全部历史研究筛选规则。

A/B 的官网、事实、目标完全相同，初始可见正文 SHA256 均为：

`d8043b21306e9672972ea04fd0d1cea8de8a3192fe3701462589ad3abed699db`

唯一业务输入差别是采集端返回的 AI 原文：

| 项目 | A：品牌缺席 | B：品牌出现但范围冲突 |
| --- | --- | --- |
| 回答原文 | 其他供应商提供设备安装与使用说明。 | Alpha不提供现场安装，仅出售设备。 |
| 策略判断 | brand_absent | fact_mismatch |
| 修改重点 | 把已核实范围组织为品牌服务问答，回应品牌缺席观察 | 优先澄清现场安装范围，纠正回答中的服务范围误述 |
| evidence freeze 完成 UTC | 18:24:46.934352 | 18:25:03.598092 |
| strategy HTTP UTC | 18:24:47.262507 | 18:25:03.980269 |
| draft HTTP UTC | 18:24:47.674125 | 18:25:04.351631 |
| 新稿 SHA256 | 0f47052ccad5fe97a8e6441e887762503f81013af1c04cd459b067fbb7234609 | 05d984dd453896b614cbe48d233f5d466fa56d8a5b8e2078f26c2d858cae978e |

以上时间均为 **2026-09-05 UTC**，来自最终定版后三个场景重新实测的服务器状态和 peer 请求事件；不是第一次验收旧源的时间或 hash。最终三个 backend 文件的 SHA256 记录在 `artifacts/business-proof/backend-proven-source.json`。

亲测断言：

1. peer 的策略分支只依据收到的 `evidence_pool.answers` 原文；draft 分支只解析收到的实际策略 instructions/facts，不读取全局 A/B 开关。全局 `answer_text` 仅控制采集端答案并在 task 创建时冻结。
2. 策略引用完整原文，Answer / Analysis ID+version / QuestionVersion / Batch / platform / observed_at 与实际采集记录一致，Unicode quote offsets 准确。
3. draft 模型请求包含自己的真实 AI 引文、策略与批准事实；所有 A 模型请求不含 B 原文，反之亦然。两个独立数据库中的相同数字 ID 不构成共享数据。
4. baseline 回答收取、规则分析及证据 freeze 完成早于 strategy 与 draft HTTP；待审稿时恰有 1 次 baseline collect、0 次 WP 写入。
5. 两例的修改理由、expected_change、acceptance_method 和实际批准正文均不同；不是只比较字段复制或测试源码。
6. 精确发布授权后，各收到 **1 次真实 WP POST**，正文与批准 after_text 完全一致；公开 URL GET 包含完整批准正文，版本与 job verified；后台自动 retest，最终各 **2 次 collect / completed**。
7. retest 故意保持各自原答案，不伪造效果增长。A 提及 0/1→0/1，B 1/1→1/1；推荐/事实语义保持 unknown，小样本与非因果限制真实保留。最终结果跳过双方无样本的空分组，没有隐去有效分组的 unknown。
8. 最终策略池的 `analysis_runs` 按 run ID 只保存一份完整冻结输入，回答引用 `analysis_run_id`，不再每条重复 `analysis_input`；最终 HTTP 场景再次验证通过。

安全 trace 仅保存时间、请求类型、payload 摘要/hash、业务引文、正文 hash、状态和外部写次数；不保存 Authorization、Basic 或 API key。主要摘要：`artifacts/business-proof/differential-summary.json`；完整安全事件记录：`A.json`、`B.json`。

## 无证据与失败边界

**本验收人亲测**：独立无 Source、无历史 AI 回答、sample=false 场景，策略为 `website_hypothesis`，明确“官网内容假设：梳理已核实范围，暂无AI回答证据”；answer evidence 为空，acceptance 同样明确无 AI 证据，collect=0。人工批准的页面内容仍可执行 1 次受控 WP 更新并核验，但结果保持 `awaiting_observation`，没有称为已知 AI 问题或 GEO 成效。证据：`hypothesis.json`。

**业务逻辑 owner 报告，非本验收人重复亲测**：

- `python -m pytest tests/test_agent_runtime.py -q`：12 passed，56.09s。
- `python -m pytest tests/test_agent_strategy.py -q`：10 passed，64.80s；包括虚构 quote、错误 answer/fact/URL、只截部分回答却声称品牌缺席、inconclusive、预算/假设、旧未提交稿重新形成证据策略、反馈与重启。
- 既有 approve_only 零外发等安全覆盖保留，本轮没有重复全部安全审计。上述错误 answer ID 覆盖不冒称独立真实跨项目场景。

## 正式环境与前端边界

本轮独立验收前只读正式 health / agent-worker / openapi / projects；health=ok、database=ok、worker running=true、projects=[]。未读取用户密钥、cookie 或 `.env`；未创建正式验收项目。

重启前已对 `frontend/src` 及 package/config 普通源文件共 **21** 个文件记录 SHA256，清单为 `artifacts/business-proof/frontend-source-before.json`；没有扫描 node_modules 或 .next 源树。另只记录既有默认 `.next/BUILD_ID` 的 hash，用于确认复用原 production bundle，不进行 frontend build。正式一致备份、原 production 重启及重启后核对结果在完成后补充实际记录。
