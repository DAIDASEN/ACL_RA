# 本地筛选运行与审计

老师的 `src/teacher/select_passages.py` 原件未修改。新增入口只改变读取和计算调度，仍用老师的日期、最低点赞数、文化/题材词、命名实体、对话比例、窗口、种子和分档规则。

## 本轮环境

`experiment_02_provenance/.venv-screening/` 为独立 Python 3.13 筛选环境，避免影响先前 Python 3.14 API 小测环境。依赖版本见 `requirements-screening.lock.txt`，包括 spaCy 和 `en_core_web_sm`。

下载的五个文件已逐一计算 SHA-256，并与 Hugging Face 本地下载 metadata 的 etag 对照；全部匹配，revision 一致。详情见 `configs/download_verification.json`。Parquet 字段检查通过，共 265174 条帖子。

## 三种计算入口

| 入口 | 用途 |
| --- | --- |
| `src/screen_passages.py` | 保持原始主流程，使用逐批 Parquet 读取，记录日志与配置；作为串行参考 |
| `src/screen_passages_batched.py` | 批量 NER 验证入口，保持窗口顺序/结果；全量时完整 Doc 序列化较慢 |
| `src/screen_passages_parallel.py` | 正式自动筛选使用：并行处理原文，工作进程只返回实体标签，父进程保持筛选与采样顺序 |

Linux 版本的并行入口使用 fork。它没有改变人工判断或实验设计，也没有调用模型 API。

在工作区根目录重跑全量时必须使用**新的输出目录名**：

```bash
experiment_02_provenance/.venv-screening/bin/python -u \
  experiment_02_provenance/src/screen_passages_parallel.py \
  --outdir experiment_02_provenance/data/processed/candidates/YOUR_NEW_RUN \
  --n-process 32 --batch-size 64 --progress-every 5000
```

## 一致性验证

在同样的前 1000 帖、种子 13、min-score 2 下，两种加速版本的 `candidates.csv` 与 `candidates_all.csv` 均与串行参考逐字节一致；578 段通过，所有过滤统计一致。结果见 `reports/SCREENING_ENGINE_EQUIVALENCE_20261107.json`。

并行版对每篇的前六个打乱窗口做相同过滤，按原次序取第一个通过者。即使并行提前计算了后续窗口的实体结果，也不改变选择。输出保留源帖子/评论位置，可追溯到本地数据。

## 输出与审核

- `candidates_all.csv`：所有自动通过片段，按老师原规则在 prompt 去重前输出；不是全部通过人工审核。
- `candidates.csv`：约 200 段待审样本；默认实际上是高中低各 66，共 198。各档不足时可能更少。
- `run_metadata.json` / `filter_stats.log`：输入版本、软件、参数、代码哈希、状态和过滤统计。
- `configs/active_candidates.json`：本轮正式进入审核的候选文件指针；验证试跑的 P000 等 ID 不能与活动批次混用。
- `src/build_passage_review_pack.py`：从活动候选生成审核表、隐藏来源/分档的阅读包，以及三份独立合理性检查表；人工判断全部留空。

候选文件的 passage_id 只在各自批次内唯一；跨批次用 run_id + passage_id 关联，源追溯用 story_id/prompt_id。不能混合不同筛选批次的判断。

审核通过后仍需逐模型记忆检查，才可定稿 120 段。此时不生成评分结果，不把自动通过改写为人工通过。

## 本轮活动材料

全量原规则结果位于 data/processed/candidates/full_worker_20261107；额外辅助预筛位于 data/processed/candidates/priority_20261107。优先阅读包在 validation/review/priority_20261107，统一入口是 [START_REVIEW.md](../START_REVIEW.md)。额外规则不属于原始算法，完整记录见筛选报告与 priority_metadata.json。

全量结果的前 20000 帖、6043 段保留文本及来源字段与串行参考一致；两个 198 段集合均已逐段追溯回原文并再次执行原始单段规则。规则通过不等于语义上没有科幻或文化线索。
