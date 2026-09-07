# Agent-first GEO 运行与审核

主流程是 **用户选项目、说业务目标；Agent取证、规划、改稿与执行；人只审核必要决定**。高级运营API继续保留，不要求用户登记空Content、搬运ID、逐页点击fetch/generate/publish/sync/verify。完整字段见 [agent-api.md](agent-api.md)，原始服务的安全与人工发布边界见 [operations.md](operations.md)。

## 正常一轮

1. 使用已有品牌/官网项目。配置能力API只返回布尔值和安全原因，没有服务器密钥。没有模型则ready=false且start=503，不运行模板替身。
2. 输入本轮目标，选1–3页与模型请求上限；采样只有已登记Source且服务器采集能力可用时才可选。持续维护默认关闭；显式选中后，在计划审核中确认。
3. 后台先持久冻结同项目官网/有效事实/现有问题及有限历史回答、固定Analysis版本、诊断、有来源审核研究与规则，再真实模型选页和计划。最新6批次、最多12条完整有效回答、每条最多12,000字符、180天窗口；超长回答排除而非截断后推断品牌缺席。平台/区域/QuestionVersion/采集模式与条件保留，不混成排名。页面、AI原文、研究和反馈都是**不可信数据**，不能扩大工具权限或自动成为品牌事实。
4. 审阅计划的页面、真实客户问题、引用、改稿指令、预期改变、验收标准及模型主观商业判断。不是搜索量、市场需求实测或算法知识。新增事实候选严格逐字引用本轮HTTP快照，**网页营销声明不自动变为已验证事实**；人工须核对真实性后批准。已有人工事实不会被改写；当前有效且claim和source_url完全一致的Fact复用，过期或不同出处不擅自合并。
5. 计划批准后事务性物化原Question/QuestionVersion、Opportunity、Action和Content。已授权采样时，**先自动baseline创建→collect→持久sync完成→规则analyze，再调用一次真实模型细化优化诊断/策略，最后生成稿件**；没有技术按钮需要用户推进。策略逐条引用Answer/Analysis版本/QuestionVersion/Batch/平台/观察时间及精确quote，或网站snapshot；完整回答支持品牌缺席，误述需批准Fact与原文，观察和原因假设分开。策略输出真正进入生成指令并冻结到ContentVersion.generation。输入返回后再核对事实/问题/来源/目标/标题，主动HTML与未批准URL本地拒绝。
6. 人看before/after、事实引用、来源快照、目标与副作用，直接批准或写退回意见。退回实际调用模型形成**新提案与新版本**，旧审核/意见保留。高级工具改了旧事实/标题后，仍可拒绝或退回；退回重新取证进入新计划epoch，不死锁在失效稿。
7. `approve_only`只确认稿件，绝不外发；随后是明确发布授权提案。`approve_and_publish`必须绑定完整目标URL、page、不可变version、正文SHA256及显示标题，并显式allow_publish。无需再次点击技术性发布按钮。
8. WordPress能力可用时，待审稿已只读核对资源id/link并冻结该资源正文hash和modified_gmt。发布前再次GET核对，变化则阻塞，不能旧授权覆盖后来编辑。服务器WordPress根地址、HTTPS、凭据、资源归属门禁沿用原服务；唯一Job先预留，再单次POST已批准正文/标题。**GET→POST之间仍有短竞态窗口，WordPress接口无CAS，不声称原子覆盖保护。**
9. 提交成功不等于上线。Agent自动只读同步、GET公开页核验完整批准正文。未知提交只读恢复，绝不重POST。Action done仅表示内容执行完成，不是GEO目标达成；结果reason展示具体策略→内容变化→同条件复测实际提及命中/分母、推荐/事实unknown、可比性和小样本限制。无样本空分组跳过；有样本而有效分母为0显示unknown，不显示成已测0分。
10. 若持续维护已获批准，到期由同一持久runner生成唯一关联child run：自动取新证据、检查当前有效事实、生成新计划待审；不会自动批准或公开。关闭持续模式则只完成本轮并安排时间，不在到期暗中调用模型。取消停止后续步骤/未来维护，不声称撤销已经开始的提交。

## 观测与不确定性

计划授权且有Source时，复用原monitoring服务在**生成稿件之前**完成冻结baseline、collect一次、自动sync、持久规则analyze，之后单次策略模型细化。全部页面verified后按同baseline冻结问题版本/采集源/条件创建retest、collect/sync/analyze/compare。不重写Razormind。每轮一个已批准Source、最多3个问题；正常pending自动等，每2秒检查、单次最长300秒、每阶段最多300次；cursor持久递增。未知提交、确认要求、真实错误或超时明确blocked，不重发collect。

规则Analysis不偷偷增加语义调用，推荐/事实字段保持unknown。独立strategy_model可依据原文和批准事实给出语义判断，**不覆写、不伪称原Analysis已做语义分析**。所有收费调用先持久step并计入max_model_requests；默认8次可容纳发现1+计划1+策略1+最多3稿=6。没有同问题历史AI证据且不开采样时，仍可明确执行“官网内容假设优化（无匹配AI回答证据）”，在summary/expected_change/acceptance_method显示，不冒称AI回答驱动。

非WordPress保留原外部人工发布：内容approve_only后，由操作者在外站发布并通过existing external-publication登记，system_issued_write=false。Agent安全恢复只读核验已有记录，不伪装通用CMS能力。外部发布前未采baseline时不能事后补成“干预前”样本。

策略ready必须完全保持批准的页面、URL、问题与事实范围，每个判断有精确支持证据；没有证据或invalid时blocked/inconclusive，不生成“已优化”的假稿。需要新增facts/pages/questions/publisher等范围时返回新plan提案，重新人审。研究/规则只作其适用条件下的有条件假设参考：最新审核修订必须有核验证据，refuted/inconclusive、当前来源已改或超过180天保守引用窗均排除，未知适用条件不包装成现行validated规律。

历史旧run若已批准稿但尚无任何PublicationJob，撤销旧发布checkpoint后重新取证→策略→新不可变稿件→新审阅，不凭新baseline替旧稿补依据。已有外部job的旧run不重发：仅恢复已有记录并明确“旧稿并非基线策略驱动”；部分目标已提交则阻断后续发布。历史提案不改写；缺少干预前证据不事后补造。

## 配置与持久性

- 模型：服务器`OPENAI_BASE_URL`（默认OpenAI v1）、`OPENAI_API_KEY`、`OPENAI_MODEL`。生产代码复用真实`model_json`/`generate_content`HTTP请求和严格Pydantic/引文校验，无假fallback。
- WordPress：`WORDPRESS_URL`、`WORDPRESS_USERNAME`、`WORDPRESS_APPLICATION_PASSWORD`，项目登记已有pages/posts resource。凭据只在服务器，默认HTTPS；仅服务器精确GEO_HTTP_ALLOWLIST允许受控literal loopback HTTP。
- 采集：`RAZORMIND_URL`、可选`RAZORMIND_API_TOKEN`，项目已有真实Source。
- 原授权：`GEO_BACKEND_TOKEN`；本地审核identity不是新增身份认证系统。外部部署仍须保护前端与后端。
- 执行器随FastAPI lifespan启动：单执行线程，数据库条件UPDATE claim、300秒租约、20秒心跳。页面关闭不会停止run。网络/模型调用不持有长数据库事务；短写授权门禁用真实SQLite写锁/数据库行锁串行取消与批准。唯一run/key检查点与原领域唯一job防重复物化和外部提交。
- graceful停止保存当前已完成工具输出、释放lease；重启继续剩余步骤。硬中断且模型没有完整持久结果时blocked为unknown，不自动重复计费调用。未知WP提交复用原PublicationJob，恢复只GET。
- `/agent-worker/health`报告线程可用及安全reason。已知DB busy/deadlock等瞬态安全等待；意外编程错误停止worker、报告unready及安全异常类型、记录服务器日志，不吞异常后伪装健康。
- 此策略修复不新增迁移，保留head **a71d9b33e204**，复用AgentStep与ContentVersion.generation。正式数据库仅由独立验收协调人一致备份并恢复原Production；业务开发和HTTP验收均使用隔离数据库，不改前端或原`.next`。

## 上轮 Agent-first 验收记录（策略修复前）

以下都使用**明确受控协议peer**，不是实际付费模型、真实WordPress账号或AI平台GEO提升证据。生产路径真实HTTP调用，没有mock成功返回替换生产实现，也未向生产外站写入。

- 独立uvicorn **8001**、隔离SQLite `tests/.agent-smoke.db`；loopback peer **18771**支持OpenAI-compatible结构化响应、现有WP资源POST真实保存/GET，以及原Razormind协议采集。peer依据收到的当前fetch原文生成计划与事实引文，不是生产默认模板。
- 实际主循环run **3**：goal→自动抓取/模型plan→人工计划approve→自动Action/ContentVersion→request_changes“更简洁”→新不可变version **6**→明确approve_and_publish→唯一job **1**→真实POST一次→完整可见正文verified（`2026-09-05T17:48:02.721697+00:00`）→next_review_at `2026-10-05T17:48:02.733669+00:00`。用户未点击fetch/generate/publish/sync/verify。没有采样，结果awaiting_observation。
- 前端独立浏览器run **4**：plan52→draft57→反馈→draft61 revision2→明确授权→job2自动verified；刷新保持真实run，桌面/移动截图由前端保留，未把浏览器当执行器。
- 真实采样run **7**：Source1、baseline pending→completed，干预后retest pending→completed，全程没有手动sync。真实UTC：baseline接收 **17:53:20.041860** < job创建 **17:53:20.131944** < 首次核验 **17:53:20.357330** < retest接收 **17:53:23.537159**。两次collect、一次WP POST，最终descriptive_comparison，未声称GEO提升。
- 维护throwaway场景仅推进隔离库的due时间：未授权持续模式run3 **无child、无新增模型调用**；已授权run7到期后自动产生唯一child **8**，真实新快照 **18/19**和新模型plan待人工审核，WP POST计数不增加。
- 独立安全复核见 [agent-review.md](agent-review.md)：真实HTTP验证错/陈旧授权、并发审核、长模型取消、旧提案拒绝、新epoch改稿、未知提交重启只读恢复。发现的缺失import与失效稿不能拒绝问题均已修复并独立复验。
- 永久回归只覆盖易错门禁：无模型不假运行、越权URL/假引文/主动HTML、并发与旧审批、approve_only零写、标题/官网正文陈旧、未知提交幂等、反馈新版本、相同有效事实复用、pending采样自动推进、模型期间事实编辑/取消、worker异常真实unready。原测试fixture显式把后台Session也切到临时SQLite，避免测试后台碰正式库。
- 最终最新源码完整回归：`python -m pytest tests -q --tb=short` → **118 passed in 115.53s**（原106 + Agent12）。前一轮完整运行118 passed in115.74s；最后计划失效409/历史提案状态收尾后再次全量复验，以上为最终输出。
- PostgreSQL仅离线编译：`DATABASE_URL=postgresql+psycopg://geo:offline@127.0.0.1/geo_platform python -m alembic -c backend/alembic.ini upgrade head --sql` exit0，包含a71d9b33e204；未连接PostgreSQL，不冒称运行验收。最后停止本worker的8001/18771并删除隔离smoke数据库及WAL/SHM，保留受控peer作为真正安全回归依赖。

实际平台账号/模型密钥未提供，因此不能声称已调用真实商业模型或生产WordPress、也不能声称获得实际GEO提升。配置完成后的同一生产代码路径仍执行严格审核与发布门禁。

## 本轮业务决策修复证据

- 失败前证据由独立无reload uvicorn HTTP获得：出待审draft时已完成发现/计划/稿件模型请求，但collect tasks为空；第三次请求只有instructions/before_text/facts；批准发布后才首次baseline。原记录见ignored `artifacts/business-proof/old-ordering-summary.json`，没有重复采样去“确认”用户已报告问题。
- 本轮自有真实uvicorn 8001 / controlled peer 18771 smoke：自动批准采样后，baseline GET completed早于draft模型HTTP；待审稿时1个采集任务、0外写，明确稿件批准后共2collect、唯一1次WP POST、完整正文GET verified、同baseline复测completed。实际reason为非品牌题提及0/1→0/1，推荐/事实unknown1→1，小样本效果未确定；未称GEO提升。
- 独立HTTP A/B：同官网、facts、goal，仅改变采集原文；A完整回答品牌缺席→品牌问答focus，B原文错误服务范围→澄清focus。不同策略精确引用不同原文，后续draft真实请求携带自己的策略和引用，正文hash/改稿理由/验收不同；各1WP POST+2collect。无Source路线独立验证为明确官网hypothesis。详见 [business-execution-proof.md](business-execution-proof.md)。
- 永久回归防守新增易错业务合同：原文改变实际产物、baseline先于生成、假quote/跨池Answer/未批准Fact与URL/片段缺席拒绝、inconclusive不产稿、budget拒绝追加计费、反馈/重启不重采样与refine、历史Analysis冻结、旧已授权未写稿重新审阅、旧已写记录不重模型/POST。固定模型阶段总次数不是测试契约。
- Controlled peers只是协议fixture，不是真实商业模型推理能力、实际WordPress账号或GEO提升证明。正式模型/WordPress配置缺失时仍明确不可用，不能替代真实业务效果评估。
- 定版源码完整回归：`python -m pytest tests -q` → **130 passed in 170.11s**（原118 + 12个策略业务风险用例）；此前首轮129 passed in174.63s。定版payload后独立A/B与hypothesis重新实际HTTP验证并更新源码hash，不拿旧进程结果替新源码。
- 最终自有HTTP smoke run2再验证deduplicated analysis_runs和可读结果，无0/0空分组；8001/18771已停止，自有`artifacts/business-proof/strategy-smoke.db`及WAL/SHM已删除。没有临时smoke脚本写入仓库；隔离协议证据由独立验收保留，正式Production恢复由其在finalready后执行。
