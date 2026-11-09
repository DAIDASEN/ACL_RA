# 实验二文本准备：从候选到 120 段定稿

本文将老师需求拆成操作步骤，不改变选材标准。2026-11-07 已完成真实语料的全量自动筛选，并建立辅助优先审读队列；真人与记忆检查仍待完成。`data/templates/` 保留空表模板，当前材料从 [开始审核](../START_REVIEW.md) 进入。实验一生成的故事不能代替本实验要求的人类原始文本。

下载入口、已核实版本和命令见 [数据集下载说明](DATASET_DOWNLOAD.md)。

## 你需要参与的部分

你主要负责审读候选、记录去留/修改，并落实 2–3 位合理性检查者。下载、自动过滤、表格整理、记忆探测和最终校验可以由程序完成。合理性判断必须来自实际读者，不能直接用模型结论填成人工完成。

## 1. 先筛一个候选池

老师指定数据源：`euclaise/WritingPrompts_preferences`，来自 r/WritingPrompts。记录实际下载日期、数据集 revision/文件清单和脚本哈希。数据集的许可标签不等于每篇用户原文可以直接公开，公开按老师要求处理。

原始脚本自动执行：

- 只取 2022-11-30 之前的评论故事，排除机器人/管理内容及短回复。
- 按连续段落截取 150–300 词，保留句末边界。
- 过滤人名、地名、机构等命名实体，以及文化/宗教/体育、英语俚语、明显科幻奇幻等词表命中。
- 排除对话比例过高；按点赞数分三档取样，候选集中每个 prompt 最多一篇。

先安装完整筛选依赖和 spaCy 英语模型（现有 `.venv` 仅验证了 pandas 模拟流程，不代表筛选环境已就绪）。在实验目录运行：

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m spacy download en_core_web_sm
mkdir -p data/processed/candidates/trial_001
cd data/processed/candidates/trial_001
../../../../.venv/bin/python ../../../../src/teacher/select_passages.py \
  --max-posts 20000 --seed 13 --n 200 > filter_stats.log 2>&1
```

这是通用试筛命令；本轮已改用独立 .venv-screening 和本地 Parquet 完成全量筛选，无需重复执行。先看 `filter_stats.log` 和真实保留数，再决定是否全量跑。全量使用新目录，去掉 `--max-posts`；不要覆盖已经人工填写的表。当前默认候选最多为 198 段（每档 66），不一定正好 200。

候选不足时先记录哪类过滤误伤，再按老师允许的方式考虑调低最低点赞阈值、补 candidates_all 或修订词表，保留配置和变更说明。不能为了凑满 120 而静默放宽标准。

## 2. 人工审读 candidates.csv

逐篇检查以下问题，填 `keep_manual=yes/no`，原因写 `notes`：

| 要检查什么 | 处理 |
| --- | --- |
| 来源过于明显 | 地名、品牌、节日、宗教、体育、特定食物或制度提示明显出处时排除 |
| 英语专属表达 | 双关、押韵、方言拼写、明显俚语导致不适合假设为译文时排除 |
| 题材 | 科幻、奇幻情节排除；不能仅因片段出现一个词就替代人工判断 |
| 完整性 | 场景/关系完全看不懂、截断导致不可评价时排除 |
| 可评价性 | 可以有一般或较低质量，但差到无法评价的排除；不要只选好作品 |

只有一两个人名的片段，可依老师要求改成 she/he 并保留。在 `neutralized_edits` 记录具体替换；原始候选另存只读备份，审核版的 passage 放修改后文本。避免修改剧情、润色或改写风格，最终词数必须重新检查。

例：`keep_manual=no`，`notes=依赖英语双关，译文身份不合理`。例子只是填写方式，不是实际审读记录。

## 3. 找 2–3 人独立做合理性检查

使用 `validation/templates/plausibility_review.csv` 的副本，每位读者各填一份，询问：

> 如果说这段英文是从中文、约鲁巴语、印地语或法语翻译而来，或者是尼日利亚、印度作家直接用英语写的，你觉得是否合理？

每个读者逐来源记录判断及理由；任何一位觉得不合理，该段排除。全部通过才把候选总表 `plausibility_ok` 填 yes。待审或无法判断不能直接填通过。老师要求的合理性检查范围以原文为准，不自行把它解释为模型能否猜对国家。

## 4. 对最终修改版做逐模型记忆探测

选好模型后，用原始 `probe_memorization.py` 对所有待用模型分别检查。把人工审核通过且已完成修改的候选另存 `candidates_for_probe.csv`，保留 passage_id、passage。

在实验目录运行以下示意命令（需替换真实模型/渠道，并用环境变量提供密钥）：

```bash
.venv/bin/python src/teacher/probe_memorization.py \
  --passages data/processed/candidates/trial_001/candidates_for_probe.csv \
  --model MODEL_ID \
  --out data/processed/memorization/MODEL_ID.csv
```

原始探测脚本缺少可靠续跑、失败记录和完整 token 日志，实际运行前应先补齐这些功能；不要直接批量花费。不要重复追加同一份探测结果。给模型前 60% 续写，出现连续至少 10 词重合或 LCS 比例 ≥0.5，按当前规则标记 memorized。

任一待用模型标记 True，该段排除并在总表 `probe_recognized` 填 yes；所有计划模型都已检查且无标记才填 no。未测试、报错或只查了一个模型应保留 pending。探测无命中不证明训练集中没有该文本。

## 5. 选 120 段并定稿

筛选逻辑：`keep_manual=yes` 且 `plausibility_ok=yes` 且 `probe_recognized=no`，并确认全部计划模型探测完成。最终选高、中、低档各约 40；点赞档只辅助覆盖质量，不等于经过验证的文学质量。

- 每段 150–300 词；一个 prompt 最多选一篇，不能有重复正文。
- 保持 passage_id 稳定，以便追溯来源、修改、读者和模型探测。
- 最终文件为 `data/processed/final/final_passages.csv`，只保留 `passage_id,passage`。
- 保留完整审核版 candidates.csv、原始备份、逐人检查表、逐模型探测结果、filter stats 和修改记录。
- 若通过不足 120 段，继续补候选和完整审核，不能用待审段落占位。

最后运行：

```bash
python src/manage.py validate-passages
```

此命令只检查技术格式、数量、ID、重复文本和词数，不替代人工判定。把 120 段定稿和全部记录交老师，按汇报节点进入预实验。

## 预实验材料还有一个容易忽略的问题

老师原脚本直接 `head(20)` 取前 20 段，而候选/定稿可能按高中低档排列。准备预实验时应让老师确认一个固定、覆盖质量档次的 20 段子集，单独保存其 ID/顺序。不要因为“前 20 段刚好全是高分档”而误判评分没有分散。

## 首次交付给老师什么

filter stats、候选和通过数（分档）、排除原因计数、少量有争议的例子、2–3 人合理性检查与模型探测安排、定稿材料及预实验子集方案。当前还没有这些实际审核结果，不能把本指南写成选材已完成。
