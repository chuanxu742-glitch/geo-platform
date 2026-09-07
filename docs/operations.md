# GEO 优化与运营：运行手册

产品主线是有据优化与日常运营，不是把AI回答监控改名。观测采样仍保留，用作冻结基线和复测验收；首页显示真实机会、任务、审核、待发、待核验与维护下一步。完整字段见 [operations-api.md](operations-api.md)，历史采集与分析见 [api-contract.md](api-contract.md)。

## 一次可执行的运营循环

1. 维护品牌事实：每条写明claim、来源URL和有效期；维护真实客户问题，问题编辑保留版本。
2. 在机会地图选问题，填写决策阶段、人工业务价值/适配、内容缺口、优先级。证据不明就明确hypothesis，不生成搜索量或保证推荐的假机会。
3. 登记项目官网同origin的既有页面，显式HTTP抓取。阅读状态、跳转、标题/meta/正文/headings/canonical/robots/JSON-LD及不可变hash/时间。失败是failure/unknown，不是低分；手动HTML导入标manual_import，不冒充抓取。
4. 从机会或finding创建原Action：owner、due_at、acceptance_method必须齐全。todo→in_progress；有真实阻塞则blocked+原因；人工评审待办用awaiting_review。完成由操作者按验收条件明确确认。
5. 为已有页面创建Content，从选定成功快照与有效facts生成新ContentVersion。人工编辑无模型依赖；model模式确实调用配置的OpenAI兼容接口并执行严格本地结构/事实ID/引文校验，缺key明示503。任何模型稿都是pending，不自动公开。
6. 人工审核版本，填写reviewer/note，approved后才可显式发布。新版本必须重新审核；事实归档、过期或claim/source等编辑后旧批准稿失效。
7. WordPress单次真实更新既有资源，之后GET目标公开URL核验完整可见正文。执行成功、URL200、version marker均不等于verified。
8. next_review_at到期后操作者显式check-due，重新抓取/核验并创建或复用维护Action。没有默认外部访问、计费定时器或自动再发布。
9. 基线在干预前采集，复测在干预后采集，保持问题版本/平台/采样/分析依据/未变对照。保存实验假设、主要改变、窗口、实际观测时间、局限；只在证据、指标区间与时序符合时标“当前观察支持”，不作因果承诺。
10. 外部平台资料必须显式抓取研究来源，或关联有效Answer/HTTP快照的精确引文，再经人工review。普通URL不能直接变validated。可复用规则冻结完整支持来源与适用条件/局限。

## WordPress：真实可运行路线与边界

只实现WordPress5.6+ REST已有`pages`/`posts`资源更新，不新建文章、不提供泛CMS发布抽象、不保留本轮没有动态官网写入能力证据的Razormind workflow发布器。原Razormind回答采集不受影响。

服务器环境：

```dotenv
WORDPRESS_URL=https://example.com
WORDPRESS_USERNAME=your-editor-account
WORDPRESS_APPLICATION_PASSWORD=your-wordpress-application-password
```

这是独立Application Password，不是登录密码，也不读取cookie。不要把凭据粘贴到前端发布器表单、source config、版本正文或提交仓库。配置发布器只填：

```json
{"name":"官网服务页","site_url":"https://example.com","resource":"pages","post_id":17,"enabled":true}
```

`site_url`须匹配项目官网origin及服务器WORDPRESS_URL完整根地址；支持已部署WordPress子目录。编辑账号需有对应资源更新权限。远程站点必须HTTPS；只有管理员显式allowlist的literal loopback可HTTP协议测试。认证请求不跟随任何重定向，防止凭据被发往其它目标；公共网站抓取也有DNS钉住和逐跳SSRF检查。

发布先GET `/wp-json/wp/v2/pages/17` 核对响应id和link与登记target URL完全相同，不能仅因为同站就覆盖另一篇。审核/事实/配置/资源归属全部通过后，数据库预留唯一版本/页job并commit，再POST同资源 `{content:批准原文,title:内容标题,status:"publish"}`。原文可含WordPress支持的HTML或纯文本；不自动Markdown转换、不额外塞品牌关键词。

- 缺服务器配置：503，未发写请求。
- 401/403等明确拒绝：execution_failed，不当已发布。
- timeout/不完整响应/无法证明提交结果：submission_unknown，绝不自动重POST。
- 2xx且id/link/status正确：awaiting_verification，尚未证明页面正文已更新。
- 重复点击：返回相同job，不重复外部更新；sync只GET资源，verify只GET目标页。
- 全部批准可见正文匹配：verified，并保存不可变HTTP快照/响应hash/核验时间。
- 页面正文不匹配：verification_failed；可再次只读核验，不盲重发。

人工在外站操作后可用external-publication登记，system_issued_write=false，保持独立外部记录语义；必须同审核与事实门禁，并且仍需正文verify。旧`/content-versions/{id}/publish`已删除。历史published_at原样保留但只是未验历史声明，不授予新复测资格。

静态核验排除script/style/template/head/hidden/aria-hidden与inline display:none/visibility:hidden。HTML批准稿按其可见文本规范化匹配，标记不能独立通关。**核验仅证明采集时静态HTTP正文匹配；不执行JavaScript或完整外部CSS，不证明引擎索引、收录、引用或GEO改善。**

## 抓取与平台技术事实

官网Page只能属于项目官网；外部研究来源使用独立ResearchSourceSnapshot，不能绕过发布归属限制。两者均由明确POST启动抓取，GET列表不会联网。正文2MiB/robots256KiB、超时与5次跳转边界，禁止递归全站crawler。默认拒绝私网、回环、metadata、URL凭据和非HTTP(S)；受控内网只由服务器`GEO_HTTP_ALLOWLIST`精确授权，不能由请求body开放。

以下是诊断参考的**平台技术文档事实，不是用户实测优化效果证据**，不会seed为研究支持结论：

- [Google：AI features and your website](https://developers.google.com/search/docs/appearance/ai-features)：AI Overviews/AI Mode没有额外技术门槛、特殊schema或专用机器文本文件要求；重要内容可用文本、结构化数据与可见内容一致、可抓取是一般Search实践。Googlebot控制Search；Google-Extended不等于Google Search。
- [OpenAI：Overview of OpenAI Crawlers](https://developers.openai.com/api/docs/bots)：OAI-SearchBot是搜索，GPTBot是训练，两者控制独立；ChatGPT-User的用户访问不等同Search资格判断。允许robots不证明实际被索引/引用，禁GPTBot不自动成为GEO故障。
- [WordPress REST Pages](https://developer.wordpress.org/rest-api/reference/pages/)：更新已有页面使用POST `/wp/v2/pages/<id>`，content/title/status可写，id/link用于响应核对。
- [WordPress REST Authentication](https://developer.wordpress.org/rest-api/using-the-rest-api/authentication/)：WordPress5.6+ Application Password通过HTTPS Basic认证，使用独立应用密码而非浏览器会话。

不要求llms.txt，不以字数/FAQ数量/markup推断真实排名或算法掌握。

## 迁移与用户数据

保留初始迁移`2e4666322eb1`原文；新增`3712685b1ab1`（运营模型、扩展Action/ContentVersion）及`9c371d04b221`（外部研究来源）。旧ContentVersion审核默认pending，不以published_at猜已验发布；旧用户稿件、行动、问题/回答/分析历史不重seed、不改写。

正式数据操作由操作者先停止写入、做一致性备份后执行`python -m alembic -c backend/alembic.ini upgrade head`或正常启动自动升级。SQLite有WAL时不要只复制geo.db主文件当一致备份，应使用SQLite backup API或停止写入后整体备份。开发验收全部使用隔离数据库；正式geo.db未被本后端worker删除/重seed。正式备份、升级及服务恢复由前端/主代理统一管理，避免并发迁移和端口争用。

新导入Answer缺省或null observed_at持久为本次接收时间，并在raw._geo_observation_time注明server_received；明确历史时间则provided_observation。自动采集仅使用明确的有时区observed_at，否则同样标接收时间fallback，不能猜record.created_at就是实际观察。旧缺失或无时区时间不回填，实验可保留为inconclusive并提示重新采样。

## 本次验证记录

- 第一轮整合命令：`python -m pytest tests -q --tb=short` → **99 passed in 55.05s**。最终同命令在观察时间缺省与干预先后门禁修复后 → **106 passed in 51.44s**：原22例保留并迁移新审核发布消费者流程，加1例接收时间回归、33网站安全/快照、39研究/三指标/先后时序、11发布/迁移回归。
- 真实独立uvicorn运行8003、空SQLite，受控WP协议peer18769。临时命令`python tests/.operations_smoke.py`成功输出`status: passed`、`external_write_count: 1`：机会→实际HTTP快照→人工明确导入finding→原Action→真实先采baseline→ContentVersion→approved→受控peer真实POST→完整可见正文verified→显式维护→真实后采retest→同analysis basis实验supported→外部研究HTTP来源supported→带来源运营rule。这里的回答是明确受控人工样例，**不是实际AI平台提升实测**；没有生产账号写入或计费模型调用。
- 最终时序复验从另一个空库真实执行同smoke命令，省略observed_at以覆盖新API接收时间默认，而不是手造早于运行的观察时间。实际UTC：baseline最后接收 `2026-09-05T17:28:14.769239+00:00`，job创建 `17:28:14.851783+00:00`，首次成功核验 `17:28:14.959688+00:00`，retest最早接收 `17:28:15.018870+00:00`。冻结publication_timeline.status=known，experiment=supported，符合真实前采样→发布→核验→后采样顺序。
- 老schema升级回归：先升级到初始revision，插入独立代表性用户项目/Action/ContentVersion与published_at，再upgrade head；原稿/别名/状态/时间保留，review_status=pending，publication_jobs为空，`PRAGMA foreign_key_check`无错误。
- PostgreSQL只执行离线SQL编译：`DATABASE_URL=postgresql+psycopg://... python -m alembic -c backend/alembic.ini upgrade head --sql`，exit0，生成**501行/15971 bytes**，包括三revision。未连接PostgreSQL，不冒称运行验收；Docker daemon缺失是已知阻塞，本轮未重复检查或操作Docker。
- 独立审阅的真实HTTP安全与发布边界见[operations-review.md](operations-review.md)：错WP link零写入、hidden/script/marker不verified、私网跳转拒绝、未知提交只读恢复且写计数不增加。
- `tests/operations_peer.py`是永久回归依赖的loopback-only协议fixture，保留；临时smoke脚本、独立smoke进程和数据库在证据记录后清理。UI联调8001/18765由前端完成确认后再释放，不抢占正式8000/3000。
