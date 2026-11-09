# 老师固定情节提取提示

来源：`docs/TEACHER_REQUIREMENTS.md`。提取器只接收原始故事，不接收实验条件。当前未实现调用。

```text
Extract only facts explicitly supported by the story. Return JSON with goal, triggering_event, central_conflict, decisive_action, and outcome. Use 15–35 English words per field where possible. Replace personal names, country names, and place names with generic references. Do not add a genre label. Preserve relationships, institutions, objects, and causal mechanisms that matter to the plot, even if culturally specific. Use "not stated" if the information is absent. Do not infer motives, repair the story, or evaluate cultural authenticity. For each field provide a short supporting quotation in a separate evidence object. Story: {STORY}
```

五个值必须是字符串，证据单列；证据不参加嵌入。提取原始响应和修订版分开留存。没有信息填 `not stated`；内容错误不能靠反复调用挑选满意版本。
