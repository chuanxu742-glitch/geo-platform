# GEO 运营工作流独立审查

## 范围与结论

本次独立审查覆盖发布能力是否真实存在、人工审核与旧接口切换、WordPress 更新前资源身份核对、发布正文核验、未知提交恢复、受控本地例外与重定向 SSRF 边界，以及前端凭据隔离。没有把任务完成、WordPress HTTP 成功或页面 HTTP 200 当作 GEO 提升或正文上线证据。

独立黑盒使用真实启动的 FastAPI（127.0.0.1:8002）、系统临时目录内的全新 SQLite 数据库，以及独立受控 HTTP 协议服务（127.0.0.1:18767）。所有请求均为本机隔离请求，没有连接真实 WordPress 账号、运行 Razormind 平台、访问用户浏览器会话或发布外站内容。协议服务可记录收到的更新次数、返回不同页面正文与错误资源身份；它不是实际 WordPress 安装。因此下述结果证明本应用的 HTTP 协议和安全边界，不是 WordPress 生产部署端到端验收。

## 独立执行的黑盒证据

| 场景 | 实际结果 |
| --- | --- |
| WordPress GET 返回正确资源 ID、但 `link` 指向同源另一页面 | 发布 API 返回 422；受控服务收到的 CMS POST 数为 0。 |
| 正确 ID/link 的既有页面更新 | 受控服务实际收到一次 `POST /wp-json/wp/v2/pages/17`；应用仅标记 `awaiting_verification`，没有直接标记已核验。 |
| 批准全文仅存在于 `script`、`template`、`hidden` 属性元素、`display:none` 元素 | 四次真实页面 GET 核验均为 `verification_failed`。 |
| 页面仅含发布标记注释、没有批准正文 | 核验为 `verification_failed`。 |
| 批准全文实际存在于可见 `main/p` 正文 | 核验变为 `verified`，证据的 `matched_by` 为 `visible_body`。前述多次核验没有增加 CMS POST 次数。 |
| robots 仅禁止 GPTBot、明确允许 OAI-SearchBot | 保存的观察为 `GPTBot=false`、`OAI-SearchBot=true`，未将训练抓取限制当作搜索抓取封禁。 |
| 管理员只允许 `127.0.0.1:18767`，该页面跳转到未允许的 `127.0.0.1:18768/private` | 保存失败快照，错误为 `destination_not_public`；没有因初始主机已允许而放行下一跳。 |
| 更新已被 HTTP 对端接收，但提交响应缺少可核对资源身份 | 应用保存 `submission_unknown`；再次提交相同版本/页面返回 200 并复用同一 job；随后只读页面核验恢复为 `verified`。对端 CMS POST 总数在恢复前后均为 2，没有重发。 |

可见正文核验仍只是页面内容观察，不证明索引、AI 引用、排名、用户推荐或优化因果。静态 HTML 解析的这些受测隐藏形式也不等于浏览器完整 CSS/JavaScript 渲染可见性证明。

## 源码审查与已纠正的契约问题

### 发布适配器必须有真实可执行能力

只读核查 Razormind 源码后，否定了“任意已发布 workflow 接收 GEO inputs 即可更新官网”的假设：

- `backend/api/v1/studio_schemas.py` 的 `PublishedWorkflowRunStart` 接收通用 `inputs`；`backend/schemas/workflow.py` 的 `WorkflowRunProjection` 与 `WorkflowRunNodeState` 没有 `outputs` 字段，不能臆造 `data.outputs.url` 或 `nodeStates[].outputs`。
- `backend/plugins/capability_catalog.py` 的 HTTP 请求节点明确为 `plugin_required`；`compat/dify_graphon_runtime/policy.py` 的 HTTP 节点即便允许网络仍返回 `network_adapter_required`。
- `backend/workflow/opencli_hda_tracer.py` 中 TurboPush、BBX、OpenTabs 的对应执行路径读取静态节点 binding/toolParams，没有把本次 GEO 稿件输入绑定为 CMS 正文。TurboPush 平台表也不是官网 WordPress 更新连接器。

以上具体证据已交给后端与前端责任代理。最终产品改用真实可实现的 WordPress REST 既有 `pages/posts` 更新路线；未保留未经证明的 Razormind 动态官网发布宣称。原监测 Razormind 采集通道不属于此次发布替换。

### 审核与旧发布接口切换

通过源码及 AST 检查确认：

- `backend/app/content.py` 不再提供旧的 `/content-versions/{identifier}/publish`；前端旧 `actions.tsx` 不再调用该路径。
- `backend/app/publishing.py` 的实际写接口是 `publish-jobs`。预留前要求不可变版本审核通过、存在可见正文、事实当前有效且未被编辑/归档覆盖、目标与登记页面及项目官网归属一致。
- 新版本独立审核；已有发布记录版本的审核被冻结。此次只对相应源码进行审查，没有将其表述为本次独立黑盒覆盖的所有并发情形。
- 页面 URL 在已有快照或发布引用时不可改写的防护由主代理源码确认，本独立黑盒没有重复执行该场景。

### 凭据不会通过发布表单配置

- `PublisherCreate` 的实际字段只有 `name/site_url/resource/post_id/enabled`；前端发布配置表单同样没有 API key、用户名、Application Password、Cookie 或 Basic Authorization 输入。
- `publishing.py::wp_headers` 从服务器 `WORDPRESS_URL/WORDPRESS_USERNAME/WORDPRESS_APPLICATION_PASSWORD` 读取配置并在服务器生成 Basic Authorization；带凭据请求要求 HTTPS，仅管理员明确允许的字面回环地址可用于受控 HTTP 验收。
- 浏览器经 Next 同源代理访问后端；`GEO_BACKEND_TOKEN` 由服务端路由注入。通用输出脱敏覆盖 WordPress 用户名与 Application Password。此次未读取任何真实凭据。

### 运营下一步连接

后端已补充 `ready_to_publish` 与 `awaiting_verification` 及相应 `next_steps`。审查发现前端 `operations.tsx` 原导航规则未匹配新的 `kind=verify`，会错误进入任务区；该问题现已修正并由前端责任代理通过真实浏览器覆核关闭：审核通过稿进入首页待发队列，提交后进入待核验队列，实际点击 `kind=verify` 下一步后页面主标题为“内容与发布”而非计划，随后只读同步与正文核验成功。此为前端代理提交的真实 UI 验证证据，不属于本报告作者独立执行的黑盒测试。

## 验证边界

本次没有运行项目全套测试、格式化或 lint，没有修改他人正在实现的源文件。数据库迁移保留真实旧历史、研究来源抓取及实验统计完整性、艺术化 UI 的全流程浏览器交互由主代理与对应后端/前端 smoke 负责；不在本报告的独立运行证明内。生产 WordPress 的权限、插件兼容性、页面模板渲染与真实官网发布仍需在操作员明确授权的部署环境验收。

审查结束后停止独立 8002/18767 进程，关闭本机 HTTP 客户端并删除本次系统临时目录（包括受控服务脚本与隔离数据库）；不触碰正式 `geo.db`。
