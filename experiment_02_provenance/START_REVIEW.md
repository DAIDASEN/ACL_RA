# 从这里开始审核文本

自动初筛已完成。请先用下面的优先队列开始读；它是辅助预筛材料，尚未经真人或记忆检查，不是最终 120 段。

1. 打开 [阅读包](validation/review/priority_20261107/reading_pack.md)，按随机次序读正文。
2. 对照 [审核表](validation/review/priority_20261107/review_sheet.csv) 的 R 编号，在 keep_manual 填 yes/no、notes 记理由，填实际 reviewer_id 和日期。
3. 先看 [助手抽读意见](validation/review/priority_20261107/assistant_preview.csv)：R048、R180、R188 建议排除；R056、R114 需核查；R122 仅建议继续人工审读。助手只抽读了 6 段，不能当作全部审过。
4. 把相同阅读包分别交给 2–3 人，分别填写 [读者1](validation/review/priority_20261107/plausibility_reviewer_1.csv)、[读者2](validation/review/priority_20261107/plausibility_reviewer_2.csv)、[读者3](validation/review/priority_20261107/plausibility_reviewer_3.csv)。判断不同假设来源是否合理，任何一人认为不合理即排除。
5. 尚未完成所有待用模型的记忆检查，probe_recognized 留空/pending；不要直接填 no。合理性尚未完成时，plausibility_ok 也保留待定。

主要去掉来源明显、英语双关/俚语、科幻奇幻、夹杂作者说明或不可评价的片段。一般或较低质量不等于必须去掉。仅一两个人名可按老师要求改成代词，逐项记录，不改原始候选备份。

优先队列 198 段，高/中/低各 66；6 段的助手意见单列，其他段全部待审。如果最后不足 120，可从 82,184 段备选池补充。

完整结果、额外预筛规则和局限见 [筛选报告](reports/PASSAGE_SCREENING_20261107.md)。老师原规则的 [198 段抽样](data/processed/candidates/full_worker_20261107/candidates.csv) 另行保留。优先队列额外利用 prompt 线索和 POS，定稿前应向老师说明。
