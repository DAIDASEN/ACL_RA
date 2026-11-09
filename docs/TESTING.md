# 离线测试说明

2026-11-09验证：实验一12项通过；实验二在筛选虚拟环境中6项全部通过，无跳过。测试不调用收费API，不生成研究样本，也不验证研究假设。

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s experiment_01_narrative/tests -v
PYTHONDONTWRITEBYTECODE=1 experiment_02_provenance/.venv-screening/bin/python -m unittest discover -s experiment_02_provenance/tests -v
```

## 实验一：12项

| 测试 | 检查内容 |
| --- | --- |
| 预实验完整性 | 生成576条不同ID的请求；同配置重复构建结果一致 |
| 提示正确性 | OPEN删除类型句，NONE删除国家句；英美国名冠词和固定措辞正确 |
| 防缺失和篡改 | 缺请求、重复组合、私自增加提示语都会报错 |
| 正式阶段限制 | 未确认或模型仍为pending时拒绝构建正式请求；满足条件时生成5760条计划 |
| 公式方向 | 用虚构数字核对D_typed、Delta及相对NONE的差值方向 |
| 同文与自身配对 | 独立请求生成相同文本仍保留；同一story_id不与自身计算距离 |
| 分组和缺格 | 行顺序不影响汇总；样本不足返回missing；混入其他国家时报错 |
| 密钥文件读取 | .env中的文本不会被当成Shell命令执行；日志脱敏函数能替换密钥 |
| 用量缺失 | API未给token时保留unknown；给出时正确读取总量和推理明细 |
| 小测设计 | 8条小测按英国/中国×OPEN/恐怖×2组成，ID唯一并隔离在interface_test阶段 |
| DeepSeek凭据路由 | 独立密钥使用对应地址；共享密钥只使用显式配置的共享地址；配置不全报错 |
| 两模型小测一致性 | 小测提示一致、ID分离；DeepSeek使用预设关闭思考参数及2500输出上限 |

## 实验二：6项

| 测试 | 检查内容 |
| --- | --- |
| 最终文本输入 | 检查条数、唯一ID、重复正文及150–300词范围 |
| 原始脚本未改 | src/teacher四个脚本与原始ZIP逐字节一致 |
| 来源完整性 | 来源清单中的原件SHA-256保持一致 |
| 阅读包行为 | 不改候选原件、不自动填人工通过；阅读包隐藏来源prompt，拒绝覆盖已有输出 |
| Parquet分批读取 | 不同批大小读取后，行顺序和字段值与原始读取方式一致 |
| 评论列表对齐 | 正文、点赞和时间列表长度不一致时立即报错，避免错配 |

最后两项依赖pandas和pyarrow。默认Python缺少依赖时自动跳过；项目已有.venv-screening包含依赖，本次在该环境中全部通过。

原件完整性两项测试需要各实验本地docs/source及internal/source中的Context.txt、SOURCE_MANIFEST.json；这些材料默认被.gitignore排除，因此仅下载GitHub代码的环境会跳过这两项。其余测试仍按各自依赖运行。离线通过不代表API续跑、统计分析或完整预实验流程已经实现。
