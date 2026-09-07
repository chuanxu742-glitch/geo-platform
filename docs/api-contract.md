# GEO API 契约

后端前缀 `/api`，JSON body，列表直接返回数组、对象直接返回对象，错误固定 `{ "detail": "中文错误" }`。ID为整数；时间为ISO8601 UTC/带时区字符串；证据start/end为Python Unicode码点索引（start含、end不含），前端应直接显示quote或用Array.from(text)切片，不用UTF-16 string.slice。

前端仅访问同源 `/api/backend/*` 代理；代理服务器配置 `GEO_API_URL=http://127.0.0.1:8000` 和可选 `GEO_BACKEND_TOKEN`，不使用NEXT_PUBLIC后端地址/密钥。后端配置同名token后业务路由要求 `Authorization: Bearer ...`。`/api/health`不需要token。默认无token只供本机操作员使用；对外必须启用访问保护。源服务/模型凭据只取服务器环境变量，API不回显令牌字段或已配置密钥，原始任务result/record仅以脱敏视图输出。

优化运营主流程与新增端点见 [operations-api.md](operations-api.md)：机会/计划 → 页面抓取与有据诊断 → 原Action/ContentVersion修订 → 人工审核 → WordPress既有资源真实更新 → 完整可见正文核验 → 到期维护 → 平台研究/固定实验/运营规则。原回答采集与监测作为观测验收能力保留，不再是产品首页主体。

## 项目与配置 CRUD

- `GET /projects`、`POST /projects` `{name,brand,aliases?:string[],website_url?:"",region?:""}` => `{id,name,brand,aliases,website_url,region,created_at}`。
- `GET /projects/{id}`、`PATCH /projects/{id}`（上述字段可选）、`DELETE /projects/{id}`。有业务数据/历史时删除409。
- `GET /projects/{id}/competitors`、`POST ...` `{name,aliases?:[]}` => `{id,project_id,name,aliases}`；`PATCH /competitors/{id}` 可更新上述字段；`DELETE /competitors/{id}`。旧批次保存独立竞品快照。
- `GET /projects/{id}/facts?include_archived=false`、`POST ...` `{claim,source_url,valid_from?:ISO8601,valid_to?:ISO8601}` => `{id,project_id,claim,source_url,valid_from,valid_to,archived,created_at}`。source_url必须不含凭据的HTTP(S)地址。valid_from省略默认创建时间，valid_to为排他上界。`PATCH /facts/{id}` 修改当前事实；`DELETE /facts/{id}` 归档，不破坏旧快照/内容依据。
- `GET /projects/{id}/questions?include_archived=false` => `{id,project_id,archived,current_version:{id,question_id,version,text,branded,intent,region,created_at}}[]`。
- `POST /projects/{id}/questions` `{text,branded:boolean,intent?:"",region?:""}`；`PATCH /questions/{id}` 上述字段可选，每次生成新的不可变版本；`DELETE /questions/{id}`归档；`GET /questions/{id}/versions`返回所有历史版本。已归档问题不可编辑，新建基线不可使用，但旧基线复测继续使用原版本。
- `GET /projects/{id}/sources?include_archived=false`；`POST ...` `{name,platform,source_id,parameter_mapping?:{question:"question"},parameters?:{},result_mapping?:{text:"normalized_data.response",sources:"normalized_data.sources",status:"normalized_data.status"},mode?:"browser",answer_complete?:false}` => 配置对象含id/project_id/archived。`PATCH /sources/{id}` 同上可选；`DELETE /sources/{id}`归档。
- 参数映射question的值是远端source配置的真实参数名（例如text/question），不是固定query。结果映射使用点路径，可选role、complete。text可映射Role/Text数组路径，仅Assistant/AI/Model行加入正文；User/System行永不当正文。标量Text若角色映射缺失则unknown；明确response字段可直接作为回答正文。answer_complete默认false；只有操作员确认该采集器返回完整原文才启用。截断标记仍unknown，不会因任务完成认定有效。配置禁止token/key/cookie等字段，凭据只从服务器环境取。

## 冻结采样与回答

- `GET /projects/{id}/batches` 返回批次数组。
- `POST /projects/{id}/batches` `{name,question_ids?:int[],source_ids?:int[],mode?:"manual",sampling?:{},baseline_batch_id?:int,action_ids?:int[],content_version_ids?:int[],control_question_ids?:int[]}` => batch `{id,project_id,name,mode,status,snapshot,baseline_batch_id,action_ids,content_version_ids,control_question_ids,created_at}`。
- 新基线必须question_ids非空；无source时默认manual，**必须sampling:{platforms:["平台名",...]}**。自动采集必须source_ids，平台按source快照冻结。sampling可保存用户声明的模型、轮数、地区、温度、模式等方案，但后端不会凭空执行未实现的采样重复；实际一次collect为每question×source创建一个任务。
- snapshot包含冻结questions版本、sources完整配置、brand/aliases/website_url/region、competitors、facts、sampling。修改项目/别名/竞品/事实/源/问题不会改变旧批次；默认重分析沿用快照，只有显式use_current_aliases可在新分析版本中使用当前别名。
- 复测提供baseline_batch_id即可省略question_ids/source_ids/mode/sampling；复用原版本和完整采样快照。显式传入不同条件返回422。control_question_ids省略继承基线；显式[]取消（compare给警告）。对照必须属于快照，且不能是所关联行动的直接目标问题。关联内容版本必须存在verified发布job（批准完整可见正文核验），published_at或未核验人工声明不足。
- `GET /batches/{id}` => batch加answers和jobs。
- `POST /batches/{id}/import` `{answers:[{question_version_id,platform,text,task_status?:"completed",validity?:"valid"|"invalid"|"unknown",invalid_reason?:"",complete?:false,observed_at?:ISO8601,sources?:[{url,title?:"",type?:"reported"}],raw?:{}}]}` => 回答数组，201。仅manual批次可导入；平台必须属于冻结sampling.platforms，问题必须是冻结版本。允许空正文以保存失败证据，但会判invalid。默认validity=unknown、complete=false，操作者必须明确确认真实完整正文。observed_at用于历史回答事实有效时间判定；新导入省略或null使用本次服务器接收时间并持久保存，raw._geo_observation_time注明provided_observation/server_received及received_at（若输入含同名键，保留在original_input_value）。不回填旧Answer。自动采集优先明确的normalized_data.observed_at或record.observed_at有时区时间，否则同样注明接收时间fallback，不能把源record创建时间猜成实际观察时间。
- Answer `{id,batch_id,question_version_id,job_id,record_key,platform,text,task_status,validity,invalid_reason,complete,observed_at,sources,source_state,extracted_sources,raw,created_at}`。无修改/删除接口。原始文本保留空白，不因分析改写。
- sources缺失/null表示来源未知；[]表示观察到没有来源；非空数组来源已报告。source_state为unknown/empty/present。Citation type为reported/verified/text_url_extraction；从正文正则找到的URL另存extracted_sources，不冒充平台已验证引用、不改变source_state。来源指标仅有效回答计known/present。
- validity=valid仅任务completed、完整非空助手正文且明确有效；失败任务、System/User行、`[NO RESPONSE]`、`No response within 60s...`等通道错误不认有效。pending/running/awaiting_confirm与完整性不明为unknown。任务成功率与回答有效率不是同一个指标。

## Razormind任务（显式请求、可持久恢复）

- `POST /batches/{id}/collect` => `{jobs:[...]}`，每个question×source仅提交一次。先持久化submitting再发非幂等POST；网络/业务错误标submission_unknown，绝不自动重发。202只有task_id，不代表成功。
- Job `{id,batch_id,question_version_id,source_config_id,remote_task_id,status,error,raw_result,created_at,updated_at}`。状态pending/running/completed/failed/awaiting_confirm按源返回；ingested表示已读入记录。submitting/submission_unknown需要操作员核实远端，进程重启不会重新POST。
- `POST /jobs/{id}/attach` `{remote_task_id:"已核实ID"}`仅用于submitting/submission_unknown且无远端ID的任务，绑定后可sync，不触发新任务。
- `POST /batches/{id}/sync` => `{jobs,imported,status,failed_count}`。仅completed才读取runs和分页records，awaiting_confirm保持等待。按job+record ID去重，重复sync不扩样本；同任务导入回滚不计imported。completed但无records保持completed并提示下次显式同步；不制造虚假空回答。
- 批次终态completed（全部ingested）、failed（全部failed）、partial_failed（成功失败混合）；awaiting_confirm保持待确认；其他collecting。每个回答validity独立。
- 真HTTP协议：POST `/api/v1/tasks/trigger` `{source_id,parameters}` => `data.task_id`；GET `/api/v1/tasks/{id}`、`/{id}/runs`；GET `/api/v1/records?task_id=...&page=1&limit=100`，读取data[]与meta分页；保存raw_data/normalized_data/lineage/source_id/task_id/workflow_run_id的原始record。Bearer使用环境RAZORMIND_API_TOKEN；RAZORMIND_URL为根地址。

## 分析、指标与证据

- `POST /batches/{id}/analyze` `{use_model?:false,use_current_aliases?:false}` => `{analysis_run_id,answers_analyzed,model_status}`。每次新建不可变分析版本；概览只取每个回答latest分析，不重复计算分母。use_current_aliases=true只读取同项目当前aliases，品牌主体/问题/事实/竞品/source仍冻结；input_snapshot保存实际aliases与alias_policy=current_project，否则batch_snapshot。可用修正别名重算历史原文而不重新采集，不修改旧Answer/Analysis/Batch。缺席诊断使用该AnalysisRun实际别名。整批模型校验失败回滚本次分析，不覆盖已有有效版本。
- `GET /answers/{id}` => Answer加analyses，每条分析含input_snapshot可回溯别名、竞品、事实、源与模型名/规则版本。
- Analysis `{id,answer_id,run_id,version,brand_mentioned,brand_evidence,competitor_evidence,recommendation,recommendation_evidence,competitor_recommendations,rank,rank_evidence,factual_status,factual_findings,model_status,created_at,input_snapshot}`。
- 品牌匹配只在回答正文执行，不读取问题里的品牌做命中。证据精确{start,end,quote,matched_name}；无效回答brand_mentioned=null，不算未出现。
- 推荐语义recommended=明确推荐、not_recommended=明确负面/不建议、neutral=模型成功判断无正负推荐倾向（含品牌未出现）、unknown=无模型或不确定。neutral也必须有全文或充分上下文证据，纳入推荐分母；规则提及不替代推荐。竞品同样四态。
- rank仅目标被模型明确推荐、模型确认这是推荐列表且证据覆盖相应编号条目时保存；普通流程/负面清单不算。无模型或不确定rank=null，不用0。
- factual_status为consistent/inconsistent/unknown。只对比快照内在回答observed_at（省略则created_at）时有效的事实。只要有可核实不符为inconsistent，有可核实一致且无不符为consistent，无可评估项unknown；这不是全品牌事实全覆盖证明。
- 模型环境OPENAI_BASE_URL（默认https://api.openai.com/v1）、OPENAI_API_KEY、OPENAI_MODEL。真实调用/chat/completions，使用兼容json_object + schema提示 + 本地Pydantic严格类型/额外字段校验，再验证每段原文偏移/quote及事实ID。**不是宣称OpenAI strict-json-schema协议**。未配置显式use_model=true返回503；规则分析仍可用但语义/事实unknown。未进行真实计费模型/平台调用。
- `GET /projects/{id}/overview?batch_id=ID&platform=平台&region=地区&intent=意图&group_by=platform|region|intent`。筛选可独立省略，精确匹配。默认groups按branded=false/true分开；可用group_by进一步分层（额外dimension/dimension_value），不会混合有品牌/无品牌题。未选platform表示当前全部平台汇总，前端必须标明；filters返回{platforms,regions,intents}供选择器，applied_filters回显筛选。
- 返回 `{project_id,batch_ids,filters,applied_filters,groups}`。每组：sample_count（已入库回答，不含没有record的源失败任务）、valid_count、invalid_count、unknown_count、analyzed_count、answer_ids；brand_mentions、mention_denominator、mention_rate；recommended_count、not_recommended_count、neutral_count、recommendation_denominator、recommendation_unknown_count、recommendation_rate；factual_error_count、factual_denominator、factual_unknown_count、factual_error_rate；rank_mean、rank_denominator；source_known_count、source_unknown_count。
- `metrics`含brand_mentions/recommendation/not_recommended/factual/rank/sources，每个 `{answer_ids,denominator_answer_ids,unknown_answer_ids}`可点击回溯。无分母rate/mean=null。未知数包括该指标不可评估的无效/不完整/未分析回答，不能当0。
- `competitors`为 `{name,sample_count,recommended_count,denominator,unknown_count,recommendation_rate,answer_ids,denominator_answer_ids,unknown_answer_ids}[]`；是模型推荐比例，不是提及率。

## 诊断、行动、内容、复测

- `GET /projects/{id}/diagnoses`；`POST /batches/{id}/diagnose` => `{id,project_id,batch_id,answer_id,analysis_id,kind,title,evidence,hypothesis,review_status,created_at}[]`。kind=brand_absent/fact_mismatch/content_opportunity。只从有效且已分析回答生成，绑定具体分析版本。缺席证据明确全文范围；事实不符带出处快照；内容机会基于品牌缺席与竞品正文命中而不是假定推荐。原因一律标假设。重复同分析诊断不新增重复项。
- `PATCH /diagnoses/{id}` `{review_status:"pending"|"accepted"|"rejected"}`。
- `GET /projects/{id}/actions`；`POST ...` `{title,question_ids?:[],target_page?:"",fact_ids?:[],diagnosis_ids?:[],owner?:"",status?:"todo",acceptance_method,due_at?:ISO8601|null,blocked_reason?:"",opportunity_id?:int|null,page_id?:int|null,finding_id?:int|null}`；`PATCH /actions/{id}`同字段可选；`DELETE /actions/{id}`已有内容/复测引用则409。状态todo/in_progress/blocked/awaiting_review/done/cancelled。有关联运营对象的任务强制owner/到期/验收条件，blocked须原因；复用本Action而非另建任务系统。
- `GET /projects/{id}/contents`；`POST ...` `{title,target_url?:"",action_id?:int}` => `{id,project_id,title,target_url,action_id,created_at,versions:[]}`；`PATCH /contents/{id}` `{title?,target_url?}`；`DELETE /contents/{id}`有已发布/被复测引用版本则409。
- `POST /contents/{id}/versions` `{before_text?:"",after_text,fact_ids?:[]}` => `{id,content_id,version,before_text,after_text,fact_ids,facts_snapshot,generation,published_at,review_status,reviewer,review_note,reviewed_at,source_snapshot_id,created_at}`。正文/依据不可修改；新建版本才是编辑，新版本始终pending。人工编辑无模型依赖。历史published_at只是旧外部声明，不等于审核或正文核验。
- `POST /contents/{id}/generate` `{instructions,before_text?:"",fact_ids:int[]}` => 保存同形状的新草稿。仅从用户提供且当前有效事实调用模型；本地校验使用事实ID与生成稿引文偏移。无key503，没有模拟内容。generation含method/model来源、review_required与claims。**引文校验不证明事实语义保真，生成结果必须人工审核。**
- 旧 `POST /content-versions/{id}/publish` 已删除，无兼容绕过入口。改用 `POST /content-versions/{id}/review` `{status:"approved"|"rejected",reviewer,note}`，然后显式WordPress `publish-jobs` 或 `external-publication` 人工声明，再 `/publication-jobs/{id}/verify` 核验整个批准版本可见正文。WordPress更新先校验既有resource id/link、官网归属、当前事实和审批，幂等预留后一次POST；远端成功和URL200都不算verified。完整payload/status见operations-api.md。
- `GET /batches/{id}/compare` => `{baseline_batch_id,retest_batch_id,comparable,conditions_match,analysis_basis_match,coverage_match,coverage_complete,coverage:{expected,baseline,retest},warnings,groups,platform_groups,control_question_ids,control_groups,publication_evidence,causal_claim:false}`。publication_evidence逐版本保存verified/source_kinds/verification_job_ids；旧人工声明或失效核验有明确限制，不冒已上线。覆盖按问题版本×平台检查，空复测/不同覆盖/缺失覆盖都不可直接比较；双方各格最新分析的实际别名集合或analyzer_version不同则analysis_basis_match=false、comparable=false并提示同基准重算。仍提供描述性数值及警告，未匹配样本不能当失败。
- groups元素 `{branded,baseline,retest,mention_rate_delta,recommendation_rate_delta,factual_error_rate_delta,uncertainty}`；baseline/retest为上述完整指标组。uncertainty含method、mention_difference_interval、recommendation_difference_interval、factual_error_difference_interval（分别按对应known denominator两侧95% Wilson边界相减的保守范围，不声称严格差值置信度保证）、sample_insufficient、caveat。未知不进对应分母；小样本为警告，不把30作为万能充分阈值。按非配对/独立样本描述，重复问题/平台可能相关，不作因果承诺。control_groups对实际未变问题计算同样统计；platform_groups给逐平台对比。实验另冻结分析/内容/干预时间来源，并通过时序与证据门禁，不允许仅手选validated升级。
