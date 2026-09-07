# GEO 优化运营 API

前缀 `/api`；JSON，整数ID，UTC ISO8601（时间须带时区），错误 `{detail}`。沿用原auth、CORS、同源服务端代理。GET只读；抓取、模型、发布、核验、维护检查仅显式POST触发。所有新对象复用原Project/QuestionVersion/Fact/Action/ContentVersion/Batch/AnalysisRun，无第二套任务或内容系统。

## 1. 业务问题地图、机会与运营计划

问题创建/编辑仍用原questions API，保留不可变版本。机会将问题按决策阶段、人工业务价值/适配、内容缺口与优先级分组；不是搜索量预测。

`GET|POST /projects/{id}/opportunities`；`PATCH /opportunities/{id}`。
```json
{"title":"采购者理解服务边界","question_ids":[1],"page_ids":[1],"decision_stage":"consideration","business_value":4,"business_fit":5,"content_gap":"现有服务页未说明服务范围","priority":"high","basis":"hypothesis","evidence":[],"hypothesis":"明确服务边界可能帮助采购者判断适配；尚未验证","status":"open"}
```
枚举：decision_stage=awareness/consideration/decision/retention；business_value/business_fit=1..5人工判断；priority=low/medium/high；basis=evidence/hypothesis；status=open/planned/closed。question_ids至少1项。evidence项 `{url,quote,answer_id?:int}`；basis=evidence需非空证据，hypothesis需非空假设。关联Answer须同项目有效且引文准确；普通URL+quote是操作者提供的依据，不自动核实。返回上述字段加id/project_id/created_at。

原 `POST /projects/{id}/actions` / `PATCH /actions/{id}` 新增 `due_at?:ISO8601|null,blocked_reason?:"",opportunity_id?:int|null,page_id?:int|null,finding_id?:int|null`。状态 todo/in_progress/blocked/awaiting_review/done/cancelled。运营任务（有上述关联）强制owner+due_at+acceptance_method，blocked须原因。page_id会将target_page设为登记URL；finding必须属于该page。finding/机会转任务就是原actions POST，不另建任务端点。

`GET /projects/{id}/operations/summary`：
```json
{"project_id":1,"as_of":"2026-09-06T08:00:00+00:00","counts":{"open_opportunities":1,"week_plan":1,"today":1,"blocked":0,"pending_review":0,"ready_to_publish":1,"awaiting_verification":0,"maintenance_due":0,"failed_publications":0},"week_plan":[],"today":[],"blocked":[],"pending_review":[],"ready_to_publish":[],"awaiting_verification":[],"maintenance_due":[],"failed_publications":[],"next_steps":[]}
```
上例只展示结构；实际counts与各真实列表一致。week_plan是未终态且到期不晚于未来7天（含逾期）Action[]；today是到期不晚于今日UTC末；blocked是blocked Action[]。pending_review只取每个Content最新pending版本，附content_title；ready_to_publish为最新approved且无发布job的版本，附content_title/target_url/blocked_reason（例如事实已编辑）；awaiting_verification为awaiting_verification或submitting Job[]。maintenance_due为到期、事实失效或发布异常Page[]，附maintenance_reasons；failed_publications为execution_failed/verification_failed/submission_unknown。next_steps是 `{kind:"action"|"review"|"publish"|"verify"|"maintenance",id,title,reason,href}`，包括待审核、待发、待核验、阻塞和维护；不会让approved未发或执行完成未核验从首页消失。空项目全部0/[]，不以监控比率代替运营状态。

## 2. 页面、不可变快照与有据诊断

`GET|POST /projects/{id}/pages`；`PATCH /pages/{id}`：`{url,title?:"",page_type?:"service",owner?:"",next_review_at?:ISO8601|null,review_interval_days?:30}`。URL不含凭据HTTP(S)，必须同项目website_url origin。已有快照/发布历史不能改URL；另登记新页。返回字段加id/project_id/created_at/latest_snapshot/latest_publication/maintenance_reasons。未采集快照为null。

`POST /pages/{id}/fetch` 无body；`POST /pages/{id}/import-html` `{html,source_note}`；`GET /pages/{id}/snapshots`；`GET /page-snapshots/{id}`。POST返回PageSnapshot，列表直接数组。

PageSnapshot：`{id,page_id,source_kind:"http"|"manual_import",requested_url,final_url,http_status:int|null,status:"success"|"failure",error,content_hash,html,visible_text,title,meta_description,headings:[{level,text}],canonical,robots_meta:[],json_ld:[],robots_txt:{status,url,content,agents:{"OAI-SearchBot":boolean|null,"GPTBot":boolean|null,"Googlebot":boolean|null},purposes,...},fetch_evidence,created_at,findings:[]}`。HTTP失败仍保存不可变failure/unknown，不计低分；人工HTML明确manual_import，不取robots或冒充网络采集。hash/正文/响应摘要/时间不可修改。

Finding：`{id,page_id,snapshot_id,kind,title,evidence:{location,observed,...},recommendation,severity:"info"|"warning",created_at}`，仅报告可观察的title/meta/H1/canonical/robots/JSON-LD事实，有定位证据和具体建议。无排名评分，无保证推荐效果，无llms.txt必需项。Googlebot与Search、OAI-SearchBot与搜索、GPTBot与训练用途分开；禁止GPTBot不判GEO故障，robots允许也不等于被索引引用。静态解析不执行JS或完整外部CSS渲染，证据中明确此局限。

安全：默认拒绝私网/回环/link-local/metadata、凭据、非HTTP(S)，校验所有DNS结果并钉住传输IP，逐跳重验，TLS核对原hostname；超时、2MiB正文、5次跳转边界，无全站递归。服务器 `GEO_HTTP_ALLOWLIST=host:port,...` 精确允许受控内网；非客户端参数，主机不含端口仅标准80/443。诊断失败保留safe error。

`POST /pages/{id}/draft`：`{snapshot_id,content_id,fact_ids:[1],question_ids:[1],mode:"manual"|"model",instructions?:"",after_text?:""}` => 原ContentVersion。content目标URL须匹配page，snapshot须该页成功观察。before_text取快照可见正文，generation冻结snapshot_id/source_kind/question_version_ids/questions_snapshot/instructions/review_required，source_snapshot_id绑定快照。manual需after_text；model需instructions+有效facts，复用真实模型生成及严格本地事实ID/引文偏移校验，no key=503，失败不保存假草稿。新版本总pending，不自动发布。正文可为WordPress支持的HTML或纯文本；不自动将Markdown转HTML、不额外加品牌词。

## 3. 审核 → WordPress真实发布 → 完整正文核验

ContentVersion新增review_status=pending/approved/rejected、reviewer、review_note、reviewed_at、source_snapshot_id。`POST /content-versions/{id}/review` `{status:"approved"|"rejected",reviewer,note}` => version。人/意见非空；已有发布记录审核冻结，改稿创建新版本，新版本pending。事实有效期/归档/claim或source变更会阻止旧批准稿发布，需新版本。

**旧 `/content-versions/{id}/publish` 已删除，没有兼容绕过入口。** 历史published_at原样保留但不等于核验；旧数据升级后review_status=pending。所有发布路径都有相同审核、事实和页面归属门禁。

只有正式WordPress REST路线；不提供本轮未能证实动态官网发布能力的Razormind workflow adapter，原Razormind回答采集保留。

`GET|POST /projects/{id}/publishers`；`PATCH /publishers/{id}`：
```json
{"name":"官网服务页","site_url":"https://example.com","resource":"pages","post_id":17,"enabled":true}
```
resource=pages/posts，post_id正整数，更新既有资源而非自动新建文章；无kind或workflow映射字段。返回加id/project_id/created_at。site_url同项目官网origin，服务器WORDPRESS_URL必须完整匹配该根地址（允许WordPress子目录）。服务器独占WORDPRESS_USERNAME、WORDPRESS_APPLICATION_PASSWORD；这是WordPress5.6+ Application Password，不是登录密码/cookie。API配置不存凭据。外站强制HTTPS；仅明确allowlist的literal loopback可HTTP受控测试；认证请求单跳不跟重定向、不用环境代理、不重试。

`POST /content-versions/{id}/publish-jobs` `{publisher_id,page_id}` => PublicationJob（新201，同版本/页幂等复用200）。先核准事实与归属、服务器配置；GET `/wp-json/wp/v2/{pages|posts}/{post_id}`，其id及link必须与登记目标URL完全匹配才允许写。先数据库唯一预留version/page job并commit，再POST同资源 `{content:<批准原文>,title:<内容标题>,status:"publish"}`，不静默改变稿件。

PublicationJob：`{id,project_id,content_version_id,page_id,publisher_id:int|null,source_kind:"wordpress"|"external_record",status:"submitting"|"submission_unknown"|"execution_failed"|"awaiting_verification"|"verification_failed"|"verified",error,target_url,expected_hash,config_snapshot,execution_evidence,created_at,updated_at,verified_at}`。config_snapshot冻结site_url/resource/post_id/approved_content/title；无凭据。execution_evidence保存preflight/submission/sync的http_status/id/link/status/response_hash/observed_at。远端2xx+正确id/link+publish仅awaiting_verification，不是正文已更新；401/403等拒绝execution_failed，超时/不确定响应submission_unknown。幂等复用失败/未知job，不自动重新POST。重试编辑须新版本经新审核，未知应先只读核对，避免重复外发。

`GET /projects/{id}/publication-jobs` => Job[]；`GET /publication-jobs/{id}` => job加verifications[]。

`POST /publication-jobs/{id}/sync` => job：只读GET冻结WordPress资源核对id/link/status并记录证据，不是workflow轮询；external_record无此API来源返回409。缺服务器配置503；失败不冒充成功、不重发。未知提交也可只读sync/verify恢复。

`POST /publication-jobs/{id}/verify` => job加verifications[]。实际GET登记页面保存新PageSnapshot；必须HTTP成功、最终origin仍属于官网，并在静态可见正文中匹配**整个批准版本可见正文规范化结果**（折叠空白）。script/style/template/head/hidden/aria-hidden/inline display:none或visibility:hidden中的正文排除；marker、注释、JSON-LD和URL200不能单独成功。批准HTML原文保持不变，匹配其可见文本。匹配成功verified；不匹配verification_failed，显式再verify不会再次发布。每次记录 `{id,publication_job_id,snapshot_id,status,matched_by:"visible_body"|"",response_hash,summary,verified_at}`。这只证明采集时页面正文已核验，不等于索引、收录、AI引用或GEO改善。

`POST /content-versions/{id}/external-publication` `{page_id,note,published_at?:ISO8601}` => source_kind=external_record job（新201，重复200），表示操作者在系统外已发布；execution_evidence.system_issued_write=false，不伪称系统写入。审批/事实门禁相同，仍需verify才verified。未来发布时间422。没有独立attach入口。

原新建Batch关联content_version_ids现在要求verified job；历史仅published_at/外部声明未验不能新建关联复测。旧批次仍可读取比较；compare新增publication_evidence `[{content_version_id,verified,source_kinds,verification_job_ids}]`，对历史声明/失效核验明确warning，不能冒充真实上线。

## 4. 维护运行

`POST /projects/{id}/operations/check-due` 无body => `{checked_at,checked:[{page_id,publication_job_id:int|null,status,snapshot_id}],actions:Action[]}`。只检查已到期/事实失效/发布异常登记页；有发布记录则尝试verify，事实或归属门禁阻塞也抓取保留观察但不标verified；未发布页fetch。按页复用未完成“页面维护复核”Action（owner=page.owner，缺失则明确本地操作员），填写实际到期时间、验收条件与原因。推进next_review_at至当前+review_interval_days；维护Action需人工验收完成。无自动外部网络/计费scheduler。

## 5. 平台研究与实验知识

`GET|POST /projects/{id}/research`；`GET|PATCH /research/{id}`：
```json
{"platform":"ChatGPT","channel":"官网","mode":"搜索回答","scenario":"客户判断安装服务范围","source_type":"官方说明","claim":"搜索与训练抓取控制独立","status":"hypothesis","conditions":"此文档所述机器人与公开网页","limitations":"不证明实际索引或推荐改善","evidence":[{"url":"https://developers.openai.com/api/docs/bots","quote":"待核验引文"}],"reviewer":"","review_note":""}
```
status=hypothesis/supported/inconclusive/refuted。evidence支持 `{url,quote,answer_id?:int,snapshot_id?:int,research_source_id?:int,start?:int,end?:int}`。普通URL是operator_provided；supported/refuted必须至少一条有效完整同项目Answer准确引文或HTTP成功快照的准确可见正文引文，reviewer/review_note非空。引用页snapshot_id须真实http，manual_import不冒核验来源。GET/保存research不访问外部URL。GET单项含不可变revisions，snapshot保存before/after/evidence_snapshot及变更前证据；保留完整来源与人工审核。

`POST /projects/{id}/research-sources/fetch` `{url}` 显式安全抓取外部官方/平台研究URL，不要求自有官网，绝不成为可发布Page；`GET /projects/{id}/research-sources` => ResearchSourceSnapshot[]。形状 `{id,project_id,url,final_url,title,visible_text,content_hash,status:"success"|"failure",error,http_status:int|null,fetch_evidence,created_at}`。失败也保存。采用同SSRF/边界和静态正文解析；精确来源引文及Python Unicode start(含)/end(不含)可保存/回溯，不伪造平台结论。

`GET|POST /projects/{id}/experiments`；`GET /experiments/{id}`：
```json
{"title":"服务页修订观察","hypothesis":"明确服务边界与回答表现变化相关","primary_change":"只修改服务页范围说明","page_id":1,"content_version_id":1,"baseline_batch_id":1,"retest_batch_id":2,"window_start":"2026-09-01T00:00:00+00:00","window_end":"2026-09-07T00:00:00+00:00","metric":"mention_rate","direction":"increase","conditions":"固定问题/平台/分析基准并保留未变对照","limitations":"观察性比较；重复回答可能相关，不能归因"}
```
metric=mention_rate/recommendation_rate/factual_error_rate；direction=increase/decrease。同项目页面/version/批次，retest须关联baseline和该已核验内容；对照必须冻结一致且不属于内容/Action直接目标。窗口有时区且递增并覆盖实际observed_at。冻结comparison（含treatment_groups排除controls）、双方AnalysisRun IDs、完整回答/分析/来源、content/page与control IDs，后续重分析不改旧实验。

`POST /experiments/{id}/conclude` `{status:"supported"|"inconclusive"|"refuted",reviewer,note}`。响应conclusion_gate给supported/refuted阻止原因；supported/refuted要求同分析基准、完整有效覆盖、真实对照、实际方向与对应指标保守Wilson边界差值范围支持（不跨0），未知不进各自分母。低样本提示局限，不把30当科学万能阈值；仅“当前观察支持/不支持”，绝不因用户手选validated就通过，不宣称因果或掌握算法。结论审核后不可覆盖，另建实验保留历史。

comparison另冻结publication_snapshots（含发布job、每次核验及HTTP快照）和 `publication_timeline:{status:"known"|"unknown",publication_job_id?,source_kind?,start,end,start_basis?,end_basis?,verification_id?,limitations?,reason?}`。WordPress干预开始用job.created_at；external_record开始用operator_reported_at并明示人工来源；结束一律用该job最早真实HTTP成功正文核验时间，作为保守可见上界而不是平台索引生效时间。supported/refuted必须baseline全部观察≤开始、retest全部观察≥结束，且baseline最后观察<retest最早观察。缺失/无效/倒置来源时序仍可保存实验但只能inconclusive，不回填旧时间。新人工导入缺省/null观察时间现在持久为接收时间并注明server_received；应在真实干预前后分别采样，不用伪造历史时间通关。

`GET|POST /projects/{id}/operations/rules`：`{title,instruction,conditions,limitations,experiment_id?:int,research_id?:int,reviewer,review_note}`。至少一个supported且人工review的来源；所有提供来源均须达标，冻结完整source_snapshot。适用范围/局限/审核人/意见必填，不保证跨平台复用效果。

## 操作顺序

维护品牌事实/客户问题 → 登记自有页面 → 创建证据或明确假设机会 → 显式抓取读finding → 带owner/到期/验收Action → 从快照人工或真实模型改稿 → 审核 → 配置既有WordPress资源并显式发布 → 真实GET完整可见正文verified → 到期显式维护 → 固定baseline/retest及分析 → 实验结论 → 带完整来源和局限的运营规则。无模型/发布凭据仍能完成全部人工机会规划、快照、任务、编辑、研究记录；模型或发布能力缺失明示503，不生成假结果。
