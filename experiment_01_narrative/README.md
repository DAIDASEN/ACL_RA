# 实验一：AI 故事生成与叙事重复

研究问题：明确要求故事类型后，模型生成的情节是否更多样？这种变化是否因故事发生国家而异？国家仅指发生地，所有故事用英语生成。

- [老师需求全文](docs/TEACHER_REQUIREMENTS.md)；[Word 原件](docs/source/RA_Narrative_Generation_Measurement_Guide.docx)。
- [执行计划与实现边界](docs/IMPLEMENTATION_PLAN.md)；[数据约定](docs/DATA_DICTIONARY.md)。
- [配置](configs/config.yaml)；[预实验简报模板](reports/PILOT_REPORT_TEMPLATE.md)。
- [已完成的 GPT 6 Luna 8 篇接口小测及 token 明细](reports/GPT6_LUNA_INTERFACE_TEST_20261106.md)。
- [已完成的 DeepSeek Flash 8 篇接口小测](reports/DEEPSEEK_FLASH_INTERFACE_TEST_20261106.md)；[两模型用量对照](reports/INTERFACE_TEST_COMPARISON_20261106.md)。

## 当前能做什么

已实现：按固定模板生成预实验请求表，检查组合、提示与 ID；纯 Python 的五类故事距离汇总；离线单元检查；独立的少量真实 API 接口测试及 token 记录。完整预实验采集器、自动质检、情节提取、嵌入、真人验证、bootstrap 和正式分析仍待实现。

目录中已有的 CSV 多为表头模板。`data/manifests/pilot/requests.csv` 是计划请求，不是故事或实验结果。老师原始材料没有提供本项目脚本，`src/` 中代码均为本次新增。

## 本地运行

在本实验目录下：

```bash
python src/build_requests.py --stage pilot
python src/build_requests.py --stage pilot --check-only
python -m unittest discover -s tests -v
```

默认生成 576 行、按配置种子随机排程的 `requests.csv` 和校验元信息；已有文件拒绝覆盖。改配置后请用 `--outdir` 指定新的版本目录。检查文件时必须使用与生成时相同的配置。命令从其他目录运行也会以本项目作为默认路径。

正式请求表仅在配置的 `formal_approved` 为 `true` 且生成模型已确定后允许生成；这个字段表示老师已经确认，不是工具替你批准。即使通过，也只生成请求表。

## 目录

| 路径 | 用途 |
| --- | --- |
| `docs/source/` | 原始 Word，保持不变 |
| `configs/`、`prompts/` | 待确认配置、固定提示的可读副本 |
| `src/`、`tests/` | 请求表/基础指标代码、离线验证 |
| `data/templates/` | attempts、stories、plots 数据表头 |
| `data/manifests/{pilot,formal}/` | 完整请求及随机排程，两个阶段分开 |
| `data/raw/{pilot,formal}/` | 原始故事、API 响应和 attempt 日志 |
| `data/processed/{pilot,formal}/` | 质量标记、提取、向量及 ID 映射 |
| `validation/` | 单篇/成对核对模板、独立编码和裁决 |
| `results/{pilot,formal}/` | 指标、区间、稳健性与图 |
| `reports/`、`logs/` | 预实验简报、预算、变更和实际运行记录 |

研究规则以老师原文及之后的书面确认优先。禁止为了获得更合意的内容重抽；原始响应逐条保存；真实模型/工具版本与费用不能填猜测值。

## 少量真实接口测试

用户授权使用工作区根目录 `.env` 中的 `key` 和 `base_url` 测试 GPT 6 Luna。入口 `src/interface_test.py` 只做 8 篇的固定小测，数据在 `interface_test` 路径，不能并入老师要求的 pilot/formal 样本。

```bash
# 从本项目目录运行。此命令会调用收费 API；相同 run-id 的已返回请求不重复调用。
python src/interface_test.py --run-id YOUR_NEW_TEST_RUN --limit 1
# 检查首条响应后，沿相同 manifest 继续，累计最多 8 篇。
python src/interface_test.py --run-id YOUR_NEW_TEST_RUN --limit 8
```

沿用固定系统提示和 A 模板；temperature=0.8、top_p=1、max_completion_tokens=2500、reasoning_effort=none。真实发送参数随请求保存。不自动切换模型、参数或重试；传输失败但调用状态未知时停止。脚本只用于当前兼容接口小测，不代替完整采集器。

- `data/manifests/interface_test/<run>/`：8 条计划请求、运行配置和代码哈希，无密钥。
- `data/raw/interface_test/<run>/`：逐次发送参数、完整响应、原文、持久化 attempt 日志。
- `data/processed/interface_test/<run>/`：stories.csv 和 token_summary.json。
- usage 记录输入、输出、缓存和推理 token；缺失保留 unknown。推理 token 是输出明细，不能再加一次。费用以使用平台账单为准。

DeepSeek Flash 使用独立入口 `src/deepseek_interface_test.py`，保持相同 8 个条件和提示，发送 `thinking.type=disabled`、`max_tokens=2500`。它优先读取 DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL；若只有用户明确配置的共享 key/base_url，则只在该原接口主机上使用共享密钥，不转发到新的服务主机。

```bash
python src/deepseek_interface_test.py --run-id deepseek_flash_interface_20261106 --limit 1
python src/deepseek_interface_test.py --run-id deepseek_flash_interface_20261106 --limit 8
# 以下仅汇总已有原始响应，不调用 API。
python src/summarize_interface_tests.py luna_interface_20261106 deepseek_flash_interface_20261106
```

依据 [DeepSeek 官方更新日志](https://api-docs.deepseek.com/updates/)，2026-11-06 核实时 `deepseek-flash` 是最新 Flash 别名。保存实际返回标识；若返回仍是别名，不能把文档中的更新版号充当平台已固定的精确快照。

缺失的用量字段在 `usage_accounting.json` 中保留 null，并记录缺失条数；`known_token_subtotals` 只求已知值的和，不能把其中的 0 当作缺失字段已经被确认是零。模型小测对照输出在 `results/interface_test/`，不是正式研究结果。
