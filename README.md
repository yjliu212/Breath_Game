# Breath_Game

呼吸训练小游戏（Flask）。

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

# 运行测试
python -m pytest

# 本地运行（数据库默认 instance/users.db，可用 DATABASE_PATH 指定）
SECRET_KEY=change-me python app.py
```

生产部署与数据库迁移见 [DEPLOY_NOTES.md](DEPLOY_NOTES.md)。
