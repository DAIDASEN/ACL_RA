# 上传到GitHub

目标仓库：https://github.com/DAIDASEN/ACL_RA

## 在干净副本中首次上传

当前托管工作区的.git目录只读。整理后的上传副本位于/tmp/ACL_RA_upload，仅包含.gitignore允许提交的文件，不包含数据、密钥或内部文档。副本是整理完成时的快照，之后修改工作区不会自动同步。

在服务器终端执行：

```bash
proxy_on
cd /tmp/ACL_RA_upload
git init -b main
git config user.name "DAIDASEN"
git config user.email "1155211130@link.cuhk.edu.hk"
git add .
git status --short
git commit -m "Organize research workspace for two experiments"
git remote add origin https://github.com/DAIDASEN/ACL_RA.git
git push -u origin main
```

proxy_on仅适用于已配置代理函数的服务器，其他机器可省略。首次认证时输入GitHub用户名，在Password提示处使用新生成且具有目标仓库写权限的个人访问令牌；不要将令牌放进命令、远程地址或文件。邮箱用于提交署名，不代替登录。

如果远程已有提交，改用clone后复制整理好的文件、检查差异并提交，不要强制覆盖远程历史。

## 后续更新

在可写、已经clone的工作目录中更新：

```bash
git add .
git diff --cached --stat
git commit -m "Update experiment progress"
git push
```

.gitignore不会移除已经被跟踪的文件，提交前应检查暂存内容。本次未执行上传。
