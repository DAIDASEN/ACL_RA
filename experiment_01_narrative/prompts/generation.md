# 老师固定生成提示（可读副本）

来源：docs/TEACHER_REQUIREMENTS.md。实际请求以 requests.csv 为准，构建器中的固定模板应与本副本同步。

## 系统提示

```text
You are a fiction writer.
```

## 用户提示 A

```text
Write a complete original short story in English of approximately 750 words. [GENRE] [COUNTRY] Return only the story, without a title or commentary.
```

GENRE：`The genre is {genre}.`；COUNTRY：`Set the story in {country}.`。

## 用户提示 B

```text
Create an original, complete short story of about 750 words in English. [GENRE] [COUNTRY] Provide only the story text, without a title or commentary.
```

GENRE：`Write it as a {genre} story.`；COUNTRY：`The story takes place in {country}.`。

## 用户提示 C

```text
Tell a complete fictional story in English, using approximately 750 words. [GENRE] [COUNTRY] Output the story only, without a title or commentary.
```

GENRE：`Use the {genre} genre.`；COUNTRY：`Use {country} as the setting.`。

OPEN 删除整个 GENRE 句；NONE 删除整个 COUNTRY 句。不得发出字面 OPEN/NONE，不加例子、标题或额外创作指导。
