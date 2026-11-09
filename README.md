# ACL_RA

文学与大语言模型研究：故事生成中的叙事重复，以及文学评价中的出处效应。

## 项目

| 项目 | 研究内容 | 当前进度 |
| --- | --- | --- |
| [Experiment 1](experiment_01_narrative/README.md) | 指定类型是否增加情节多样性，以及故事背景国家之间的差异 | 已完成576条请求计划及两个模型各8篇接口测试；完整预实验和测量待完成 |
| [Experiment 2](experiment_02_provenance/README.md) | 固定英文正文、改变出处说明，比较六项文学评分 | 全量自动筛选完成，198段优先审读材料待人工审核；评分实验未开始 |

当前没有正式研究效应结论。接口测试不计入预实验，自动通过不等于人工审核通过。

## 目录

```text
ACL_RA/
├── README.md
├── docs/                       # 测试及GitHub上传说明
├── experiment_01_narrative/     # 实验一：生成与叙事测量
├── experiment_02_provenance/    # 实验二：选材与出处评价
└── internal/                   # 本地汇报、私人背景及历史草稿，不提交
```

两个实验的文件分工：

| 目录 | 内容 |
| --- | --- |
| src/、tests/ | 执行代码和离线检查 |
| configs/、prompts/ | 配置与固定提示；未确定项目保留pending |
| docs/ | 设计和操作说明；老师原件及需求转写仅本地保留 |
| data/ | 模板、请求计划、原始和派生数据；仅模板默认提交 |
| validation/ | 人工核查模板和实际审核；仅模板默认提交 |
| reports/ | 阶段报告、预算模板和变更记录 |
| results/、analysis/、figures/、logs/ | 运行产物，仅本地保留 |

实验一另有prompts/；实验二src/teacher/保存老师提供的原始脚本。预实验、正式实验和接口测试分别存储，原始数据不覆盖。

## 使用入口

- 实验一：[运行说明](experiment_01_narrative/README.md)、[接口测试汇总](experiment_01_narrative/reports/INTERFACE_TEST_COMPARISON_20261106.md)。
- 实验二：[运行说明](experiment_02_provenance/README.md)、[文本审核入口](experiment_02_provenance/START_REVIEW.md)、[筛选报告](experiment_02_provenance/reports/PASSAGE_SCREENING_20261107.md)。
- 通用：[测试说明](docs/TESTING.md)、[GitHub上传说明](docs/GITHUB_UPLOAD.md)。
- 本地给老师的汇报：internal/handoff/REPORT.md；工作计划：internal/NEXT_STEPS.md。

GitHub代码仓库不包含真实文本、密钥、审核记录和私人原件，部分指向这些材料的链接仅在本地可用。

## 离线检查

在项目根目录执行，不调用收费API：

```bash
python -m unittest discover -s experiment_01_narrative/tests -v
python -m unittest discover -s experiment_02_provenance/tests -v
python experiment_02_provenance/src/manage.py status
```

实验二Parquet读取测试需要pandas和pyarrow；原件校验需要本地私人材料。缺少相应依赖或材料时，对应测试会跳过，详见测试说明。

配置使用JSON兼容的YAML格式，当前以Python标准库读取。实际研究前需要确定模型版本、参数、预算和人工审核安排，并冻结研究方案。
# ACL_RA
