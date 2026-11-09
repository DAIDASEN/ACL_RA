# DeepSeek Flash 少量真实 API 接口测试报告

日期：2026-11-06。用户授权，沿工作区 .env 显式配置的兼容接口运行；密钥未写入日志。

## 模型与运行结果

- 按 [DeepSeek 官方更新日志](https://api-docs.deepseek.com/updates/)，核实日最新 Flash 调用名为 deepseek-flash，官方对应 DeepSeek-V4.1-Flash-1017。
- 本批请求和实际返回 model 均为 `deepseek-flash`；兼容接口没有返回可验证的日期快照，不能把官方更新版号当作此次服务已固定的精确版本。
- 渠道：用户配置的 `https://api.agicto.cn/v1`；先只读查询模型清单，确认包含 deepseek-flash，再调用 8 次生成。查询模型清单不计入故事生成次数。
- 8/8 收到故事；HTTP 全部 200、finish_reason 全部 stop；没有技术重试或重复续跑调用。
- 646–862 词，平均 783.25 词，8/8 在老师的 600–900 词合规区间；是否完整故事、类型/地点遵从仍需正式质检。
- 输入 **364 token**、输出 **8121 token**、合计 **8485 token**。缓存输入为 0；推理 token 明细八次均未提供，记录 null，不能填写为已确认的 0。
- 累计调用耗时 104.952 秒，平均 13.119 秒/篇；费用需核对平台账单。

## 固定条件与参数

和 Luna 小测相同：英国/中国 × OPEN/恐怖 × 各两篇，仅 A 措辞、独立生成、相同排程种子。temperature=0.8、top_p=1、max_tokens=2500、thinking.type=disabled、stream=false。无联网或检索工具。参数格式依 [官方 Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)。

原文、请求参数、响应、request ID、模型字段、usage、时间和响应哈希均保留。再次运行相同 run-id 后，started 记录仍为 8，原始响应没有变化。

## 逐次明细

| story_id | 词数 | 输入 token | 输出 token | 总 token | 耗时（秒） |
| --- | --- | --- | --- | --- | --- |
| T_DEEPSEEK_FLASH_GB_horror_A_002 | 770 | 49 | 997 | 1046 | 14.061 |
| T_DEEPSEEK_FLASH_CN_OPEN_A_001 | 646 | 42 | 828 | 870 | 10.237 |
| T_DEEPSEEK_FLASH_GB_horror_A_001 | 758 | 49 | 1004 | 1053 | 11.299 |
| T_DEEPSEEK_FLASH_CN_horror_A_001 | 768 | 47 | 1000 | 1047 | 14.573 |
| T_DEEPSEEK_FLASH_CN_OPEN_A_002 | 834 | 42 | 1057 | 1099 | 13.347 |
| T_DEEPSEEK_FLASH_GB_OPEN_A_002 | 823 | 44 | 1055 | 1099 | 12.967 |
| T_DEEPSEEK_FLASH_CN_horror_A_002 | 805 | 47 | 1010 | 1057 | 13.186 |
| T_DEEPSEEK_FLASH_GB_OPEN_A_001 | 862 | 44 | 1170 | 1214 | 15.282 |

## 探索性阅读观察（本助手，非盲、非真人验证）

- 英国恐怖两篇都从长期空置的房屋、相近的街名和拟人化窗户切入，但一篇以账簿预示受害命运，另一篇破墙发现尸体，不能仅凭相近开头判成同一情节。
- 中国 OPEN 两篇都涉及传统工艺，但行动链分别是瓷器修复失误后的反思，以及制茶老人接受孙子的新销售方式；宽泛主题重合不等于因果序列重复。
- 中国恐怖分别使用鬼公交与鬼镜，存在民俗/灵异惯例，但还没有做成对重复评分。
- 英国 OPEN 分别是运河神秘女子和音乐盒唤起祖母记忆，也说明不指定类型仍可能生成超自然故事；这不构成 OPEN 不遵从。

每格只有两篇，不足以推断指定类型或国家的效应；没有五种指定类型、NONE、双措辞完整组合，不能计算老师要求的完整主指标。这 8 篇是接口测试，不并入 576 篇预实验。

## 文件

- data/manifests/interface_test/deepseek_flash_interface_20261106/：完整请求与配置。
- data/raw/interface_test/deepseek_flash_interface_20261106/：不可覆盖的请求、响应、故事和 attempts。
- data/processed/interface_test/deepseek_flash_interface_20261106/：逐篇 CSV、usage_accounting.json、阅读观察和验证记录。
- 完整用量以 usage_accounting.json 为准；缺失字段不会当成零。
