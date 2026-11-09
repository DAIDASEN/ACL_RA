# Reddit WritingPrompts 数据集下载

老师脚本使用的是 **euclaise/WritingPrompts_preferences**，不是名称相近、仅含 prompt/story 的其他 WritingPrompts 整理版。

- [数据集主页与字段预览](https://huggingface.co/datasets/euclaise/WritingPrompts_preferences)
- [文件下载页面](https://huggingface.co/datasets/euclaise/WritingPrompts_preferences/tree/main)
- [Hugging Face 官方下载命令说明](https://huggingface.co/docs/huggingface_hub/guides/cli)

2026-11-06 核实：仓库约 1.36 GB，train 约 26.5 万条 prompt 记录，故事在列表列 comment_texts 中；一条 prompt 可以对应多篇评论故事，不能把行数直接当故事数。包含 comment_scores 和 comment_times，正好供老师的点赞分层、时间筛选使用。

当前固定 revision：`6f0b721311a33736b19434e276f04727d5c2e213`。有五个数据文件：

```text
data/train-00000-of-00005.parquet
data/train-00001-of-00005.parquet
data/train-00002-of-00005.parquet
data/train-00003-of-00005.parquet
data/train-00004-of-00005.parquet
```

首次核实只读取了仓库元信息；2026-11-07 用户下载的五个文件已全部校验匹配，且全量自动筛选已完成，见 [当前审核入口](../START_REVIEW.md)。

## 方法一：网页下载

打开文件页，进入 data，下载五个 parquet 文件。建议放到：

`experiment_02_provenance/data/raw/WritingPrompts_preferences/data/`

需要可复现时使用上述固定 revision 的文件页，而不是以后可能变化的 main：

[固定版本文件页](https://huggingface.co/datasets/euclaise/WritingPrompts_preferences/tree/6f0b721311a33736b19434e276f04727d5c2e213)

## 方法二：命令下载到本项目（推荐用于保留本地快照）

以下是在工作区根目录重新下载固定快照的方法。本地已有完整快照，无需重复下载。

```bash
experiment_02_provenance/.venv/bin/python -m pip install huggingface_hub
experiment_02_provenance/.venv/bin/hf download euclaise/WritingPrompts_preferences \
  --repo-type dataset \
  --revision 6f0b721311a33736b19434e276f04727d5c2e213 \
  --local-dir experiment_02_provenance/data/raw/WritingPrompts_preferences
```

## 方法三：老师脚本按需读取

`select_passages.py` 已调用 `load_dataset(..., split="train", streaming=True)`，可以安装完整依赖和 spaCy 英语模型后直接筛，不必先手动下满五个文件。流式读取会产生网络传输，不等于完全不下载数据；原始脚本未固定 revision，需要额外记录来源版本。

筛选步骤见 [文本准备指南](TEXT_PREPARATION_GUIDE.md)。如果已经下载到本地，可在一个全新的候选目录中运行原始脚本，并通过 `--parquet` 传入下载的数据路径。

从实验目录执行示例：

```bash
mkdir -p data/processed/candidates/local_trial_001
cd data/processed/candidates/local_trial_001
../../../../.venv/bin/python ../../../../src/teacher/select_passages.py \
  --parquet ../../../raw/WritingPrompts_preferences/data/\*.parquet \
  --max-posts 20000 --seed 13 --n 200 > filter_stats.log 2>&1
```

这里把 glob 的星号转义后传给脚本，由脚本自己的 glob 展开；源路径相对当前候选目录。本轮已在独立 .venv-screening 环境安装并验证了筛选依赖和 spaCy 模型。自动筛出的 candidates.csv 只是候选，仍需人工审读、2–3 人合理性检查、逐模型记忆探测，最后才能定稿 120 段。
