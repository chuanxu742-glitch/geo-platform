# GEO 后端架构与运行边界

## 模块化单体

FastAPI提供`/api`；SQLAlchemy 2保存关系实体，Alembic管理版本迁移。PostgreSQL为部署目标；SQLite用于没有外部服务时的本机完整业务验证，不将SQLite验证冒称PostgreSQL实测。

- `backend/app/catalog.py`：项目、官网/地区、别名、竞品、有出处/有效窗口的事实、不可变问题版本、配置化采集源CRUD。
- `monitoring.py`：冻结批次、人工原文导入、持久化源任务、显式同步、分析/概览/复测API。
- `integrations.py`：真实Razormind HTTP及OpenAI兼容HTTP协议、角色/完整性/错误标记验证、结构化模型结果与引用校验；不读取cookie，不操作平台浏览器，不替换用户现有稳定采集通道。
- `analytics.py`：正文品牌规则证据、可选语义分析、最新版本聚合、可回溯诊断、Wilson边界描述性比较。
- `content.py`：原Action、人工/模型不可变ContentVersion与事实依据；运营直接扩展这两者，不另建task/content系统。
- `operations.py`：客户问题机会地图、官网Page、快照改稿、真实周计划/今日待办/审核/待发/待核验汇总与显式到期维护。
- `website.py`：带DNS钉住、逐跳SSRF校验、正文/时间边界的HTTP观察、不可变PageSnapshot/定位finding、静态可见正文解析；机器人搜索/训练用途分别观察，无排名评分。
- `publishing.py`：逐版本人工审核、WordPress既有资源ID/link预核对、持久幂等写预留、未知提交不重发、外部人工声明和完整可见正文核验记录。
- `research.py`：显式外部资料HTTP快照、精确引文/来源门禁、不可变研究审阅版本、冻结baseline/retest/AnalysisRun及干预时序的实验、带来源与局限的人工运营规则。
- `models.py`、`schemas.py`、`operations_schemas.py`、`db.py`、`common.py`、`main.py`：原关系模型增量扩展、typed输入约束、事务/迁移、输出脱敏、认证与启动。仍是模块化单体；无新的CMS/provider抽象，Razormind原回答采集保留但不宣称其当前节点能动态发布官网稿件。

不引入分布式队列。每次trigger先提交唯一的question-version×source job预留，再进行一次非幂等POST；中途进程退出时`submitting`仍在库内，禁止自动重发。网络异常保留`submission_unknown`，操作员在源服务核实后可绑定remote_task_id，再显式sync。轮询读completed后才读runs与分页records；awaiting_confirm不当成功。记录唯一约束(job_id,record_key)确保sync幂等。导入每个源任务事务提交后才累计新增数。混合成功/失败终态partial_failed，任务失败与回答无效分别展示。

## 历史与输入快照

问题编辑只增加QuestionVersion，已有批次继续指向旧版本。批次冻结问题、source参数/字段映射、平台/模式、用户声明采样条件、品牌/别名/竞品/事实；默认重分析与复测使用该快照，不会偷偷读当前配置。可显式传use_current_aliases=true，**仅**用同项目当前aliases重算已保存历史原文；品牌主体、问题、事实、竞品、source仍保持冻结。新AnalysisRun.input_snapshot保存实际别名及alias_policy，旧回答/批次/分析版本不变，缺席诊断依据实际分析别名。双方最新分析别名/规则基准不同则compare.analysis_basis_match=false且不可直接比较，需同基准重算。事实/问题/源归档而不破坏引用历史。

Answer正文及raw record从导入后不可通过API改写。API返回脱敏视图，数据库保留原始记录用于授权审计；数据库备份应视为敏感资产。分析新建AnalysisRun与每条Answer的递增Analysis版本；概览仅按Answer取最新分析，重算不扩大样本数。分析输入快照含规则版本与可选模型名。模型请求/校验失败整批回滚，既有分析仍有效。ContentVersion保存前后稿、事实快照、生成来源/引用、首次确认发布时间；文本修改只能建新版本。

并发版本插入与job创建有数据库唯一约束；冲突返回409，不静默覆盖。PostgreSQL使用行锁序列化批次修改；SQLite用于单机低并发，唯一约束仍防重复，忙锁返回503。初次迁移建议在单实例启动前执行，避免多副本同时迁移。未宣称高并发/多租户RBAC支持；当前为受保护的单操作员/团队私有工作台，不是公开注册SaaS。

## GEO指标语义

样本是已保存的回答record，不是问题数/分析版本数/任务202数。失败源任务若无record保留在jobs，不凭空制造失败回答。概览branded/unbranded默认分离，可按平台/地区/意图过滤或分组；全部平台汇总必须在界面明确标识。每个指标提供分子、分母、未知答案ID，便于反查原文。

规则只扫描answer正文，问题里带品牌不能导致命中。英文品牌使用词边界避免Alpha匹配Alphabet；CJK可连续匹配；每处保存精确偏移及引文。完整性默认未确认；截断/角色缺失为unknown，已知System/User、超时与NO RESPONSE为无效。普通平台原始Role/Text数组只提取Assistant/AI/Model；不把prompt当回答。

无模型或不确定时推荐/事实unknown，不当否定。模型明确推荐recommended、明确负面not_recommended、可判断但中性neutral；三种已知状态纳入推荐分母，竞品同样计算，提及率绝不冒充推荐率。排名还要求目标明确被推荐、存在明确推荐列表与覆盖编号条目的证据；无模型、普通编号步骤、负面清单都是null。

来源数组缺失/null与空数组分别unknown/empty。从正文抽取URL单列为text_url_extraction，不提升为verified或已报告引用。来源known/present指标只纳入有效回答。

事实窗口为valid_from≤回答observed_at<valid_to；手工导入历史回答可显式提供observed_at，省略使用接收created_at。采集record默认按本系统接收时间评估，若导入历史原文应使用人工路径明确observed_at，不能用今日事实自动推断过去真假。事实来源由用户提供，系统不宣称爬取核真；模型只能对比当时有效的快照事实，拒绝输入外fact_id或错位quote。

## 模型与内容安全

模型仅显式按钮/API调用，启动/浏览页面不会产生计费请求。`OPENAI_BASE_URL`需指向OpenAI兼容`/v1`根路径，使用`chat/completions`的`json_object`模式，并在system消息提供schema；随后执行Pydantic严格类型/额外字段校验、Python Unicode偏移/quote一致性校验、事实ID范围校验。没有宣称兼容strict-json-schema协议。JSON格式正确及引文精确不等于语义事实正确。

生成仅将用户选定且当前有效事实作为依据；旧稿不是事实来源，模型被要求删去无依据旧事实。输出为**必须人工审核的草稿**；生成事实引文校验不保证模型没有编造或遗漏。ContentVersion审核绑定不可变稿件，新版本默认pending；已发布版本审核冻结，事实过期/归档/编辑后旧版本不能再次发布。

官网真实发布只实现WordPress5.6+ REST既有pages/posts资源更新：服务器配置Application Password/username/站点根，发布器与官网、服务器根匹配；先GET固定ID确认link完全等于登记target URL，预留唯一version/page job并commit后单次POST批准原文/title/status=publish。401等确定拒绝为execution_failed，超时/不完整响应为submission_unknown，重复按钮复用job而非重POST；只读sync/verify可恢复。旧publish API删除，external-publication仅人工外站记录，system_issued_write=false。保留历史published_at但绝不凭它认verified。

核验保存新HTTP快照，只有完整批准可见正文规范化匹配且最终origin仍属官网才verified；200、marker、script/template/hidden正文不够。保留每次成功/失败哈希和时间，维护显式重新GET。此证明仅静态HTTP可见正文观察，不执行JavaScript/完整外部CSS，不证明搜索索引、AI引用或优化效果。

所有凭据由服务器环境设置；source配置禁止secret/token/key/cookie等字段，不探查用户会话/浏览器cookie或其它仓库配置。WordPress认证请求强制HTTPS（仅精确allowlist literal loopback可受控HTTP）、单跳不跟重定向、防SSRF与DNS重绑定，不使用系统代理。页面/研究无凭据GET可在每跳重验后跳转。网络错误不回显请求头/响应凭据，已配置密钥递归脱敏。GEO_BACKEND_TOKEN为后端共享令牌，Next同源代理只在服务器注入；远程部署仍须TLS/访问网关保护前端。

## 复测，不承诺因果

复测必须基线已有回答，冻结原问题版本/平台方案/source映射/模式，关联行动与已核验批准正文的内容版本。未变对照省略继承基线；被关联内容/行动直接修改的目标问题不能同时当对照。比较检查实际问题版本×平台覆盖与分析基准；历史未验人工声明有明确publication_evidence限制。相同覆盖不等于相同每格样本数，阅读样本/各指标known denominator与逐平台组。

提及/推荐/事实错误率分别从真实known numerator/denominator计算两侧95% Wilson边界差值，未知不进分母，范围是保守描述而非严格差值置信保证。重复问题/平台相关性、时间变化、小样本均需局限说明，30不是科学万能阈值。

研究支持/否定必须精确有效Answer或真实HTTP来源引文及人工review，普通URL不是已核验证据。外部ResearchSourceSnapshot不充当自有可发布Page。实验冻结原始回答/分析/AnalysisRun、比较与干预时间；支持/否定需同条件/基准/完整有效覆盖、真实对照、方向和对应区间支持、基线在干预前/复测在干预后；缺时间只能inconclusive，不篡改旧Answer。运营规则冻结已review supported来源、适用条件和局限，不宣称掌握算法或因果。

## 运行、迁移与验证

在仓库根目录建立独立虚拟环境，安装`backend/requirements.txt`（测试用`backend/requirements-dev.txt`，已包含运行依赖）。启动：

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

启动自动Alembic upgrade head，也可显式`python -m alembic -c backend/alembic.ini upgrade head`。默认SQLite为仓库根geo.db，空库不插入demo/虚构仪表盘。配置PostgreSQL示例见.env.example与docker-compose.yml；Compose只启动隔离数据库，应用在本机运行。Docker数据库仅绑定127.0.0.1:5433，避免碰撞已有5432。数据库持久化到Compose专用volume；销毁volume是破坏性操作，备份后由操作员决定。

```powershell
python -m pytest tests -q --tb=short
```

此机全局安装了无关seleniumbase pytest插件，`-p no:seleniumbase`仅避免其自动加载干扰本项目，不跳过任何项目测试；独立venv无该插件时可省略。也可设置`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`以完全隔离外部插件。

SQLite已执行新增完整uvicorn+真实HTTP闭环：空库创建机会→实际官网快照/诊断→Action→ContentVersion→审核→受控WordPress协议peer单次真实POST→公开URL全文verified→显式到期维护→真实先采基线/后采复测→同基准实验与研究来源/规则。受控peer是必要回归fixture，不是真实WordPress部署；原受控模型测试验证HTTP与结构化校验，不是计费模型或实平台效果。详见operations.md验证记录。

PostgreSQL未实测：本机`docker info`客户端存在但Server报`npipe ... docker_engine`不存在；`docker context ls`只有同一个default管道；`where.exe postgres pg_ctl initdb`未找到原生服务端。没有安装/启动用户Docker，没有使用用户现有库或凭据。可在有Docker daemon的环境按Compose启动后运行迁移和CRUD验证。此限制不影响已完成的SQLite全流程验证。
