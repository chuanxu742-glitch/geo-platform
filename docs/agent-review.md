# Agent-first 独立审查与 HTTP 验证

## 结论与范围

独立审查发现的两项可复现缺陷已由 runtime 作者修复，并由本审查者通过真实 HTTP 重新执行确认闭环。本报告范围内无未决审查项；不代表对所有并发交错、生产模型质量或实际 GEO 提升作保证。

验证使用独立后端 `127.0.0.1:8002`、独立 SQLite 临时数据库，以及审查者编写的受控 HTTP peer `127.0.0.1:8767`。未触碰正式数据库、3000/8000 或供前端联调的 8001，未读取生产凭据、Cookie，未向真实平台或外站发布。

Peer **不是实模型，也不是实际 WordPress**。它读取应用真实发出的 OpenAI-compatible HTTP 请求中的 schema 和当前 payload，根据实际抓取快照、URL、事实 ID 与精确引文偏移构造合法 Discovery、Plan、GeneratedContent 输出；修订稿会产生不同正文。WordPress peer 提供真实 HTTP GET/POST、资源 ID/link、正文与修改时间，并记录调用次数。该实验验证协议、持久执行和授权边界，不证明模型智能或内容优化效果。黑盒客户端不导入应用模块，不调用内部 executor，也不以预填 `done` 代替执行。

## 独立实测

| 场景 | 实际操作与观察 |
| --- | --- |
| 后台执行与必要审核 | 仅通过 HTTP 创建项目、配置受控发布器、提交 goal；后台完成抓取、模型选页、模型计划，等待计划审核；批准计划后自动生成不可变稿件并等待内容审核。未手工调用 fetch/generate/publish/sync/verify。正常明确发布授权后，后台完成外写与公开正文 GET 核验，结果为 completed/verified。 |
| `approve_only` 不授权外写 | 草稿 approve_only 后出现新的 publication_authorization 提案，WP POST 数仍为 0，没有把内容审核等同于发布。 |
| 退回使旧提案失效 | publication_authorization 退回后后台调用模型生成新 proposal ID 和 ContentVersion ID；对旧 proposal 发送 approve_and_publish 返回 409，WP POST 数仍为 0。 |
| SQLite 同提案并发批准 | 同时发送两次 approve_only，一次成功、一次 409；该 proposal 仅一条 approval 审计记录。 |
| 审核等待期间站点被别人修改 | 草稿形成后修改 peer 的 WP 正文及 modified_gmt，再明确批准发布；run 被阻断并说明 WordPress 正文或修改时间已改变，WP POST 数为 0。该证据覆盖审批等待期间的陈旧基准，不声称 WP GET 与 POST 之间具有平台未提供的原子条件更新能力。 |
| 绑定标题失效 | 在现有 Content PATCH 接口修改待审稿标题后，旧稿 approve_and_publish 返回 409，未把新标题偷偷纳入旧授权。 |
| 未知外部提交与重启恢复 | peer 实际接受一次 POST 并应用正文，但返回 503；随后暂时让只读检查也返回 503。run 阻断并提供安全恢复。重启独立后端、恢复 peer GET 后调用安全 resume，后台自行核验至 completed/verified。POST 计数保持 1→1，模型计数保持 3→3，没有重发发布或重复模型产物。 |
| 长模型请求中的取消 | peer 阻塞正在进行的模型 HTTP 响应；此时 cancel 返回 cancelled。释放模型响应后仍为 cancelled，没有生成提案，也没有追加模型调用。 |
| 批准与取消同时请求 | 对同一草稿并发发送 approve_and_publish 与 cancel；本次观察到取消先获胜、批准返回 409，最终保持 cancelled，WP POST 增量为 0。该实测不是所有可能调度的穷举证明。 |

### 发现、修复并复测的缺陷

1. **明确发布授权后发生 NameError。** 初次独立执行在 publish 阶段 failed，WP POST 为 0；源码中使用 `PublishJobCreate` 却未导入。作者补齐导入后，本审查者重新执行陈旧基准检查及真实受控发布/核验，均进入预期路径。
2. **失效草稿无法拒绝或退回。** 待审稿的 Content.title 被修改后，approve_and_publish 正确拒绝，但 reject/request_changes 也被同一 binding 校验阻断，审核回路不能重新取证。作者允许拒绝失效稿，并使退回失效稿使用新的抓取/模型 checkpoint 修订键重新形成计划。本审查者用原失效 run 重新执行：request_changes → 新抓取与新计划（proposal 62）→ 计划批准 → 新草稿/新版本（proposal 67）→ 明确发布批准 → completed/verified。另建新 run 修改标题后 reject，实际返回 cancelled，外写增量为 0。问题已解决，不作为待办保留。

## 源码审查判断（区别于独立实测）

- `integrations.model_json` 使用真实 OpenAI-compatible HTTP POST 和结构化输出校验；未配置模型时返回未就绪/503，没有固定计划或伪造模型结果作为 fallback。此项是源码判断，未在本实验中连接生产模型。
- Agent 复用原有 publication gate、事实有效性/归属检查和唯一 PublicationJob 预留；Agent 层增加 proposal/version/body hash/title/target URL 绑定，以及 WP 原始/渲染正文 hash 和 modified_gmt 基准检查。发布路径存在调用实际 publisher 前的再次授权检查，而不是只把 hash 展示在提案中。
- `lock_run` 使用 UPDATE 取得 SQLite 写锁，不仅依赖 SQLite 无效的 `SELECT FOR UPDATE`；批准记录还具有 proposal 唯一约束。独立并发实测结果见上表。
- 持久模型 step 在 HTTP 前预留、完成输出复用；未知模型调用不自动计费重试。外部发布预留与只读恢复路径分开。未知 WP 的重启行为已经独立实测，未知模型崩溃恢复未作同等故障注入。
- 网页和模型输入按不可信数据处理；选页/计划证据受到同官网目标、快照、事实 ID、精确引文校验，执行器不提供任意 shell 或任意 HTTP 写工具。这是有限源码审查，不等同于完整 prompt-injection 红队测试。

## 非本审查者独立验收的事项

- 浏览器关闭后前端任务继续、视觉优雅程度，由前端/主代理实际界面验收；本报告不把 HTTP-only 执行当作浏览器关闭测试。
- sampling 固定 sync checkpoint 缓存导致恢复时无新 GET，以及原 materialize 硬编码业务判断/品牌分类的问题，由 runtime 作者处理、主代理 smoke 覆盖；本报告不将其记作审查者独立通过项。
- 生产模型与 WordPress 部署配置、真实采集源基线/复测、持续维护到期行为、长时间运行与所有崩溃窗口不在本次独立实验覆盖范围。未采样时不得把正文核验表述为 GEO 提升；本次无实际效果主张。

## 清理

独立验证结束后停止并清理审查者管理的 8002 后端、8767 peer，以及临时客户端、peer 脚本和 SQLite 数据库；保留本报告，不新增永久测试负担。
