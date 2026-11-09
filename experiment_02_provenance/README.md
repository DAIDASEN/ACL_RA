# 实验二：LLM 文学评价出处效应

同一段英文正文不变，只换出处元信息，比较文学性、总体质量、创造力、写作能力、喜爱程度和英语自然度六项评分（1–7 分）。

- [老师需求全文](docs/TEACHER_REQUIREMENTS.md)；原始 Word/ZIP 位于 `docs/source/`。
- [执行计划](docs/IMPLEMENTATION_PLAN.md)；[原始脚本问题清单](docs/SCRIPT_REVIEW.md)。
- [数据与关联约定](docs/DATA_DICTIONARY.md)。
- [文本准备逐步操作指南](docs/TEXT_PREPARATION_GUIDE.md)。
- [Reddit 数据集下载入口与命令](docs/DATASET_DOWNLOAD.md)。
- [本地自动筛选与审计说明](docs/SCREENING_RUNBOOK.md)。
- **当前入口：[开始审核这批文本](START_REVIEW.md)**；[2026-11-07 全量筛选与辅助预筛报告](reports/PASSAGE_SCREENING_20261107.md)。
- [配置](configs/config.yaml)；[预实验报告模板](reports/PILOT_REPORT_TEMPLATE.md)。

## 现有脚本

| 顺序 | 原样保留的脚本 | 输入 | 输出 |
| --- | --- | --- | --- |
| 1 | `src/teacher/select_passages.py` | Hugging Face 数据或本地 parquet | candidates.csv、candidates_all.csv |
| 2 | `src/teacher/probe_memorization.py` | candidates.csv + 每个待测模型 | memorization.csv |
| 3 | `src/teacher/run_experiment.py` | final_passages.csv | 每模型一个 JSONL |
| 4 | `src/teacher/analyze.py` | JSONL 目录 | 统计 CSV 和 summary.txt |

四个脚本保持在同一目录，满足 analyze 导入标签定义的要求；没有修改老师的提示、标签、评分和统计代码。新增 `src/manage.py` 只做输入校验、状态查询和模拟流程，不接入真实 API。配置模板目前是决策记录，老师脚本不会自动读取它。

## 环境与离线检查

在本实验目录：

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python src/manage.py status
.venv/bin/python src/manage.py smoke
```

`smoke` 会在 `results/smoke/<时间戳>/` 创建两段明确标注的合成输入，用原始 `run_experiment.py --mock` 验证 28 条记录；不调用 API、不跑统计、不代表真实实验。缺少 pandas 时会直接提示安装。

真实采集前请先修正 [SCRIPT_REVIEW.md](docs/SCRIPT_REVIEW.md) 中的问题并记录变更；下列命令仅说明原始脚本的路径映射。

## 第一阶段：候选材料

原始筛选脚本没有输出目录参数，因此在候选数据目录运行，避免 CSV 散落在代码目录：

```bash
.venv/bin/python -m spacy download en_core_web_sm
cd data/processed/candidates
../../../.venv/bin/python ../../../src/teacher/select_passages.py --max-posts 20000
```

正式全量筛选去掉 `--max-posts`。该步骤支持联网获取语料；2026-11-07 已在独立 .venv-screening 中读取本地完整快照完成全量筛选，当前材料见 START_REVIEW.md。记录 filter stats；人工复核、合理性检查及逐模型记忆探测后定稿。

回到实验目录检查最终材料：

```bash
python src/manage.py validate-passages
```

默认检查 `data/processed/final/final_passages.csv` 的 120 个唯一 ID、两列 schema、非空和 150–300 词；同时拒绝完全重复正文。不能用工具校验代替人工文化中性、合理性和质量分层检查。

## 预实验和正式路径约定

待程序修正、材料通过及模型确定后，使用明确路径参数：

```bash
# 以下为需替换模型名的命令示意；会产生真实调用，不要直接照抄占位符。
.venv/bin/python src/teacher/probe_memorization.py \
  --passages data/processed/candidates/candidates.csv --model MODEL_ID \
  --out data/processed/memorization/memorization.csv

.venv/bin/python src/teacher/run_experiment.py \
  --passages data/processed/final/final_passages.csv --model MODEL_ID \
  --n-passages 20 --reps 1 --labels L01 L03 L05 L06 L07 L10 \
  --outdir results/pilot
```

API 密钥通过环境变量传入，非默认平台同时指定 `--base-url`、`--api-key-env`。修正后的预实验分析应输出到 `analysis/pilot/`；正式结果到 `results/formal/`，分析到 `analysis/formal/`，图到 `figures/<stage>/`。原始 analyze 目前不能直接当成完整的六标签预实验分析器。

正式实验默认每模型 120 × 14 × 3 = 5040 次，四模型 20,160 次，temperature 1。老师确认预实验后才开始；必须记录精确版本、调用渠道、实际参数、用量、成功/失败和成本。
