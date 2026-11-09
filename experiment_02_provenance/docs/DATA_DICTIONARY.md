# 实验二数据管理约定

| 路径 | 内容与关联 |
| --- | --- |
| `data/raw/` | 下载的源数据及来源/revision 记录；不把原文当作可公开材料 |
| `data/processed/candidates/candidates_all.csv` | 所有自动通过的片段；原始脚本生成，尚未按 prompt 去重 |
| `data/processed/candidates/candidates.csv` | 约 200 段候选，含 passage_id、来源、tier、人工审核/修改/合理性/记忆字段 |
| `data/processed/memorization/memorization.csv` | 每段 × 模型的续写、连续重合长度、LCS 和标记；保留探测版本/日期，避免重复追加 |
| `data/processed/final/final_passages.csv` | 最终 120 段，只含 passage_id、passage；修订应与候选审核记录对应 |
| `results/pilot/<model>.jsonl` | 预实验原始评分记录；原脚本字段 model、passage_id、label、rep、六项分数、justification、raw |
| `results/formal/<model>.jsonl` | 正式评分记录；不能混入 pilot、smoke 或不同版本模型 |
| `analysis/<stage>/` | 计数、描述、主模型、关键对比、捆绑检验、分模型和理由词表结果 |
| `validation/review/` | 独立合理性审查、最终材料审核、理由抽检原表；模板在 validation/templates |
| `logs/run_log.csv` | 实际模型版本、渠道、时间、数量、用量、费用和环境记录；API attempt 详细日志待补采集器 |

关联键：候选与定稿用 passage_id；评分记录唯一键为实际模型版本 × passage_id × label × rep。原始脚本只记录请求中的 model，需要修正后补实际版本。重复采样先在模型 × passage_id × label 内平均，再进行分析。

最终 CSV 不能直接从模板空表开始跑实验。最终校验是技术检查，人工筛选、修改轨迹、合理性和记忆结果必须另行保留。所有 CSV 用 UTF-8。
