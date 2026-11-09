# 数据与关联约定

所有 CSV 为 UTF-8，所有关联用 `story_id`，不能靠行号。配置版本和哈希随请求及结果保留。

| 文件 | 每行含义 | 核心字段 |
| --- | --- | --- |
| `data/manifests/<stage>/requests.csv` | 一个计划请求，行序为随机运行顺序 | request_id、story_id、stage、model、actual_model、country、genre、wording、replicate、batch、schedule_index、system_prompt、user_prompt、config_version、config_sha256 |
| `data/raw/<stage>/attempts.jsonl` | 一次实际调用，模板为字段说明 CSV | story_id、attempt_id、时间、实际模型、参数、request_id、完整响应/错误、finish_reason、用量 |
| `data/processed/<stage>/stories.csv` | 一个计划请求的最终状态 | story_id、选用 attempt_id、原文路径、状态、词数、语言、质量标记、排除理由 |
| `data/processed/<stage>/plots.csv` | 一篇故事的五项情节与证据 | story_id、goal、triggering_event、central_conflict、decisive_action、outcome、evidence_json、plot_text、提取器版本 |
| `validation/<stage>/coder1_*.csv` / `coder2_*.csv` | 两位真人分别提交的原始判断 | 编码者、原故事 ID、逐字段判断、证据、类型/地点/语言/完整性、成对重复分数 |
| `validation/<stage>/adjudicated_*.csv` | 负责人裁决 | 两份原始记录引用、最终判断、理由和日期 |
| `results/<stage>/summary.csv` | 一个模型 × 国家 × 措辞 | 各格 n、D_open、D_within、D_between、D_typed、Delta、Separation、配置版本/数据哈希 |

`request_id` 是本地计划请求 ID，当前等于 story_id；平台返回的 request ID 另记 `provider_request_id`。一次请求可对应多个 attempt，不能混淆二者。

原文路径：`data/raw/<stage>/stories/<story_id>.txt`；响应目录：`data/raw/<stage>/responses/`。原件只追加、不覆盖；修订另存 processed，并记录来源。

`P_M1_CN_horror_A_001` 表示预实验/M1/中国背景/恐怖/A 措辞/第 1 次；正式前缀 F。`science fiction` 的 ID 使用 scifi，但字段和提示保留原值。replicate 只作编号，不构成跨模型配对。

状态设计待采集器实现：planned → running → completed / technical_failed；返回拒绝或短故事仍算收到内容，进入质量标记，不再当作技术失败重生成。采集器需要处理中断时 running 状态及未知计费情况，不能盲目重发。
