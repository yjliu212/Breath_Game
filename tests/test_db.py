"""Database location, import-time table creation, and legacy-schema migration."""
import os
import sqlite3
from contextlib import closing
import subprocess
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, Session
from werkzeug.security import generate_password_hash

import app as app_module
from conftest import ROOT, make_app, login


def tables(db_file):
    with closing(sqlite3.connect(db_file)) as conn:
        return {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}


def columns(db_file, table):
    with closing(sqlite3.connect(db_file)) as conn:
        return {r[1] for r in conn.execute(f'pragma table_info("{table}")')}


def run_import(env_overrides, tmp_path):
    env = {k: v for k, v in os.environ.items()
           if k not in ('DATABASE_PATH', 'SQLALCHEMY_DATABASE_URI', 'WEBSITE_SITE_NAME')}
    env.update(env_overrides)
    env['SECRET_KEY'] = 'test-not-secret'
    # Import exactly like `gunicorn app:app` does (no __main__ block).
    return subprocess.run([sys.executable, '-c', 'import app; print(app.app.config["SQLALCHEMY_DATABASE_URI"])'],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)


def test_gunicorn_style_import_creates_dir_and_tables(tmp_path):
    db_file = tmp_path / 'nested' / 'dir' / 'users.db'
    assert not db_file.parent.exists()
    res = run_import({'DATABASE_PATH': str(db_file)}, tmp_path)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == 'sqlite:///' + str(db_file)
    assert db_file.exists()
    assert {'user', 'practice_session'} <= tables(db_file)
    assert 'rounds' in columns(db_file, 'user')


def test_sqlalchemy_uri_takes_precedence(tmp_path):
    uri_file = tmp_path / 'uri.db'
    path_file = tmp_path / 'path.db'
    res = run_import({'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(uri_file),
                      'DATABASE_PATH': str(path_file)}, tmp_path)
    assert res.returncode == 0, res.stderr
    assert uri_file.exists()
    assert not path_file.exists()


def test_default_paths(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_PATH', raising=False)
    monkeypatch.delenv('SQLALCHEMY_DATABASE_URI', raising=False)
    monkeypatch.delenv('WEBSITE_SITE_NAME', raising=False)
    flask_app = app_module.app
    assert app_module.database_uri(flask_app) == 'sqlite:///' + os.path.join(flask_app.instance_path, 'users.db')
    monkeypatch.setenv('WEBSITE_SITE_NAME', 'BreathGame')
    assert app_module.database_uri(flask_app) == 'sqlite:////home/data/users.db'
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'x.db'))
    assert app_module.database_uri(flask_app) == 'sqlite:///' + str(tmp_path / 'x.db')


def test_init_is_idempotent(tmp_path):
    db_file = tmp_path / 'twice.db'
    make_app(db_file)
    make_app(db_file)  # second start must not fail or duplicate anything
    assert {'user', 'practice_session'} <= tables(db_file)


# ---- legacy database built from the model code on `main` (d7fd7cf) ----
LegacyBase = declarative_base()


class LegacyUser(LegacyBase):
    """Verbatim copy of the User columns in main's app.py."""
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    username = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(150), nullable=False)
    inhale = Column(Float, default=4.0)
    hold1 = Column(Float, default=2.0)
    exhale = Column(Float, default=6.0)
    hold2 = Column(Float, default=2.0)


def build_legacy_db(db_file):
    engine = create_engine('sqlite:///' + str(db_file))
    LegacyBase.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(LegacyUser(username='olduser', password_hash=generate_password_hash('oldpass123'),
                         inhale=5.0, hold1=1.0, exhale=7.0, hold2=1.5))
        s.commit()
    engine.dispose()


def test_legacy_db_is_migrated_without_data_loss(tmp_path):
    db_file = tmp_path / 'legacy.db'
    build_legacy_db(db_file)
    assert tables(db_file) == {'user'}
    assert 'rounds' not in columns(db_file, 'user')

    flask_app = make_app(db_file)

    # Schema was extended in place.
    assert {'user', 'practice_session'} <= tables(db_file)
    assert 'rounds' in columns(db_file, 'user')
    with closing(sqlite3.connect(db_file)) as conn:
        rows = conn.execute('select username, inhale, hold1, exhale, hold2, rounds from user').fetchall()
    assert rows == [('olduser', 5.0, 1.0, 7.0, 1.5, 5)]

    # Old user can log in, sees their settings and can use the new features.
    client = flask_app.test_client()
    assert login(client, 'olduser', 'oldpass123').status_code == 302
    html = client.get('/').get_data(as_text=True)
    assert '欢迎，olduser' in html
    assert '"inhale": 5.0' in html and '"hold2": 1.5' in html

    today = datetime.now(timezone.utc).date().isoformat()
    resp = client.post('/api/sessions', json={
        'inhale': 5, 'hold1': 1, 'exhale': 7, 'hold2': 1.5, 'rounds': 1,
        'pattern': 'custom', 'local_date': today})
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()['stats']['sessions'] == 1

    resp = client.post('/save_settings', data={'inhale': '4', 'hold1': '4', 'exhale': '4',
                                               'hold2': '4', 'rounds': '8'})
    assert resp.status_code == 302

    # A restart (another import) keeps everything.
    flask_app2 = make_app(db_file)
    client2 = flask_app2.test_client()
    assert login(client2, 'olduser', 'oldpass123').status_code == 302
    assert client2.get('/api/stats').get_json()['sessions'] == 1
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute('select count(*) from user').fetchone()[0] == 1
        assert conn.execute('select rounds from user').fetchone()[0] == 8


def test_gunicorn_import_migrates_legacy_db(tmp_path):
    db_file = tmp_path / 'legacy2.db'
    build_legacy_db(db_file)
    res = run_import({'DATABASE_PATH': str(db_file)}, tmp_path)
    assert res.returncode == 0, res.stderr
    assert 'rounds' in columns(db_file, 'user')
    with closing(sqlite3.connect(db_file)) as conn:
        assert conn.execute('select username, inhale from user').fetchall() == [('olduser', 5.0)]
