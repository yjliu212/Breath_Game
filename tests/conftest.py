import os
import sys
import tempfile

import pytest

# `import app` creates the module-level app (like gunicorn does), so point it at a
# throw-away database *before* the import. Never touch instance/users.db in tests.
_IMPORT_DIR = tempfile.mkdtemp(prefix='breath-import-')
os.environ['DATABASE_PATH'] = os.path.join(_IMPORT_DIR, 'import.db')
os.environ.pop('SQLALCHEMY_DATABASE_URI', None)
os.environ.pop('WEBSITE_SITE_NAME', None)
os.environ.setdefault('SECRET_KEY', 'test-not-secret')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app as app_module  # noqa: E402


_CREATED_APPS = []


def make_app(db_path):
    flask_app = app_module.create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + str(db_path),
    })
    _CREATED_APPS.append(flask_app)
    return flask_app


@pytest.fixture(autouse=True)
def _dispose_engines():
    yield
    while _CREATED_APPS:
        with _CREATED_APPS.pop().app_context():
            app_module.db.engine.dispose()


@pytest.fixture
def app(tmp_path):
    return make_app(tmp_path / 'test.db')


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, username='alice', password='secret123', **kwargs):
    return client.post('/register', data={'username': username, 'password': password}, **kwargs)


def login(client, username='alice', password='secret123', **kwargs):
    return client.post('/login', data={'username': username, 'password': password}, **kwargs)


@pytest.fixture
def auth_client(client):
    resp = register(client)
    assert resp.status_code == 302
    return client
