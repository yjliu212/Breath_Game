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

## 中英双语

所有界面文案集中在 `i18n.py` 的 `MESSAGES` 字典里（每个 key 同时写 `zh` 和 `en`）。
语言选择顺序：`lang` cookie（页头「中文 / EN」切换，经 `/lang/<code>` 写入，有效期一年）→
浏览器 `Accept-Language` → 默认中文。新增文案时在 `MESSAGES` 加 key，模板中用 `{{ t('key') }}`；
JS 用到的文案以 `js.` 开头，会自动注入页面的 `MSG` 对象。`tests/test_i18n.py` 会检查两种语言是否齐全。

生产部署与数据库迁移见 [DEPLOY_NOTES.md](DEPLOY_NOTES.md)。
