# 部署说明（数据库迁出 wwwroot）

从本版本起，`instance/users.db` 不再随代码提交和部署。数据库位置按以下优先级确定：

1. 环境变量 `SQLALCHEMY_DATABASE_URI`（完整 URI）
2. 环境变量 `DATABASE_PATH`（SQLite 文件路径）
3. 在 Azure App Service 上（存在 `WEBSITE_SITE_NAME`）默认 `/home/data/users.db`
4. 本地默认 `instance/users.db`

目录不存在时会自动创建。应用被导入时（包括 `gunicorn app:app`）会自动执行建表/增量迁移。

## 一次性生产迁移步骤（在部署本版本**之前**执行）

> 旧版本的数据库在 `/home/site/wwwroot/instance/users.db`。新包里没有这个文件，重新部署可能把它删除或覆盖，所以**必须先备份并复制**。

1. **SSH 进入容器**：Azure 门户 → BreathGame → 开发工具 → SSH（或 Kudu：`https://<app>.scm.azurewebsites.net` → Bash）。
2. **确认正在使用的库文件**。如果 Oryx 把应用解压到 `/tmp/<hash>` 运行，实际写入的可能是 `/tmp` 下的那份：
   ```bash
   ls -la --time-style=full-iso /home/site/wwwroot/instance/users.db /tmp/*/instance/users.db 2>/dev/null
   ```
   取修改时间最新的那份作为 `SRC`。
3. **备份**（用 SQLite 在线备份 API，避免复制到写入一半的文件）：
   ```bash
   SRC=/home/site/wwwroot/instance/users.db   # 按第 2 步结果修改
   mkdir -p /home/data /home/backup
   python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
     "$SRC" /home/backup/users.db.$(date +%Y%m%d%H%M%S)
   ```
   建议同时通过 Kudu 文件管理器把备份下载到本地保存。
4. **复制到持久目录**：
   ```bash
   python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
     "$SRC" /home/data/users.db
   ls -la /home/data/users.db
   ```
5. **配置应用设置**：门户 → 设置 → 环境变量 → 新增 `DATABASE_PATH=/home/data/users.db` → 应用（会重启应用）。同时确认 `SECRET_KEY` 已设置为随机长字符串。
6. **确认启动命令**：配置 → 常规设置 → 启动命令为空（Oryx 自动使用 `gunicorn ... app:app`），或显式为
   `gunicorn --bind=0.0.0.0 --timeout 600 app:app`。不要改成 `python app.py`。
7. **部署**：合并到 main 触发 GitHub Actions（测试通过后才会部署）。
8. **验证**：
   - 用一个老账号登录，确认登录成功、之前保存的呼吸设置还在；
   - 完成一次短练习，确认统计更新；
   - SSH 中 `ls -la /home/data/users.db` 确认修改时间更新；
   - 日志流里没有 Traceback。

## 回滚

- **代码回滚**：在 GitHub 上 revert 本次合并（或重新部署上一个 commit）。旧代码只认 `instance/users.db`，回滚前把数据拷回去：
  ```bash
  mkdir -p /home/site/wwwroot/instance
  python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
    /home/data/users.db /home/site/wwwroot/instance/users.db
  ```
  新增的表（`practice_session`）和列（`user.rounds`）对旧代码无害，会被忽略。
- **数据回滚**：用第 3 步的备份覆盖 `/home/data/users.db`，然后重启应用。

## 数据库结构演进

- 新表在启动时通过 `db.create_all()` 自动创建，已有表不会被修改或删除。
- 给已有表加列时，在 `app.py` 的 `ADDED_COLUMNS` 中追加一项；启动时会检测缺失的列并执行 `ALTER TABLE ... ADD COLUMN ... DEFAULT ...`。
- 迁移只做增量，**绝不删表/删列/删数据**。本版本新增：`practice_session` 表、`user.rounds` 列（默认 5）。
- SQLite 只适合单实例：不要开启横向扩展/多实例。
