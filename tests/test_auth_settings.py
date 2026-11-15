import json
import re

import pytest

import app as app_module
from conftest import register, login


def get_user(app, username='alice'):
    with app.app_context():
        return app_module.User.query.filter_by(username=username).first()


def embedded_json(html, name):
    m = re.search(r'const %s = (.*?);\n' % name, html)
    assert m, name
    return json.loads(m.group(1))


# ---------------------------------------------------------------- auth
def test_register_logs_in_and_shows_home(client):
    resp = register(client)
    assert resp.status_code == 302
    html = client.get('/').get_data(as_text=True)
    assert '欢迎，alice' in html
    assert '注册成功' in html          # flash rendered on the home page
    assert 'id="statSessions"' in html


def test_register_duplicate_username(client):
    register(client)
    client.get('/logout')
    resp = register(client)
    assert resp.status_code == 200
    assert '用户名已存在' in resp.get_data(as_text=True)


def test_register_short_password_shows_chinese_error(client):
    resp = register(client, password='123')
    assert resp.status_code == 200
    assert '密码至少 6 位' in resp.get_data(as_text=True)


def test_login_success_and_failure(client):
    register(client)
    client.get('/logout')
    bad = login(client, password='wrong-pass')
    assert bad.status_code == 200
    assert '用户名或密码错误' in bad.get_data(as_text=True)
    good = login(client)
    assert good.status_code == 302
    assert '欢迎，alice' in client.get('/').get_data(as_text=True)


def test_auth_pages_have_viewport_and_chinese(client):
    for path in ('/login', '/register'):
        html = client.get(path).get_data(as_text=True)
        assert 'name="viewport"' in html
        assert 'lang="zh-CN"' in html
        assert 'rel="icon"' in html


def test_home_meta_tags(client):
    html = client.get('/').get_data(as_text=True)
    assert 'name="description"' in html
    assert 'property="og:title"' in html
    assert 'rel="icon"' in html
    assert embedded_json(html, 'SAVED') is None
    assert embedded_json(html, 'LOGGED_IN') is False


# ---------------------------------------------------------------- settings
def test_save_valid_settings(app, auth_client):
    # The form has no rounds field any more; saving works without it.
    resp = auth_client.post('/save_settings', data={
        'inhale': '4', 'hold1': '7', 'exhale': '8', 'hold2': '0'})
    assert resp.status_code == 302
    u = get_user(app)
    assert (u.inhale, u.hold1, u.exhale, u.hold2, u.rounds) == (4.0, 7.0, 8.0, 0.0, 5)
    html = auth_client.get('/').get_data(as_text=True)
    assert '设置已保存' in html
    assert embedded_json(html, 'SAVED') == {'inhale': 4.0, 'hold1': 7.0, 'exhale': 8.0, 'hold2': 0.0}


def test_save_with_legacy_rounds_field_still_accepted(app, auth_client):
    # An old cached page may still post rounds; it is validated and stored, not required.
    resp = auth_client.post('/save_settings', data={
        'inhale': '5', 'hold1': '1', 'exhale': '7', 'hold2': '1', 'rounds': '6'})
    assert resp.status_code == 302
    u = get_user(app)
    assert (u.inhale, u.exhale, u.rounds) == (5.0, 7.0, 6)
    assert 'rounds' not in embedded_json(auth_client.get('/').get_data(as_text=True), 'SAVED')


@pytest.mark.parametrize('value,message', [
    ('0', '轮数需在 1–50 之间'), ('51', '轮数需在 1–50 之间'),
    ('2.5', '轮数必须是整数'), ('nan', '轮数必须是整数'),
])
def test_save_with_invalid_legacy_rounds_rejected(app, auth_client, value, message):
    resp = auth_client.post('/save_settings', data=dict(VALID, rounds=value), follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert message in html and '设置未保存' in html
    assert get_user(app).rounds == 5


VALID = {'inhale': '4', 'hold1': '2', 'exhale': '6', 'hold2': '2'}


@pytest.mark.parametrize('field,value,message', [
    ('inhale', '', '吸气时间不能为空'),
    ('exhale', '   ', '呼气时间不能为空'),
    ('hold1', 'abc', '吸气后屏息时间必须是数字'),
    ('inhale', 'nan', '吸气时间必须是有效数字'),
    ('hold2', 'NaN', '呼气后屏息时间必须是有效数字'),
    ('hold1', 'inf', '吸气后屏息时间必须是有效数字'),
    ('exhale', '-Infinity', '呼气时间必须是有效数字'),
    ('inhale', '-3', '吸气时间不能为负数'),
    ('hold2', '-0.5', '呼气后屏息时间不能为负数'),
    ('inhale', '0', '吸气时间需在 1–30 秒之间'),
    ('exhale', '1e9', '呼气时间需在 1–30 秒之间'),
    ('hold1', '31', '吸气后屏息时间需在 0–30 秒之间'),
])
def test_save_invalid_settings_rejected(app, auth_client, field, value, message):
    data = dict(VALID, **{field: value})
    resp = auth_client.post('/save_settings', data=data, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert message in html
    assert '设置未保存' in html
    assert '设置已保存' not in html
    u = get_user(app)
    assert (u.inhale, u.hold1, u.exhale, u.hold2, u.rounds) == (4.0, 2.0, 6.0, 2.0, 5)
    # The page still renders valid JS literals.
    assert embedded_json(html, 'SAVED')['inhale'] == 4.0


def test_save_missing_field_is_friendly_not_400(app, auth_client):
    resp = auth_client.post('/save_settings', data={'inhale': '4'}, follow_redirects=True)
    assert resp.status_code == 200
    assert '吸气后屏息时间不能为空' in resp.get_data(as_text=True)


def test_save_settings_requires_login(client):
    resp = client.post('/save_settings', data=VALID)
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


@pytest.mark.parametrize('bad', [None, float('nan'), float('inf'), -float('inf'), -3.0, 0.0, 1e9])
def test_legacy_invalid_values_fall_back_to_defaults(app, auth_client, bad):
    with app.app_context():
        u = app_module.User.query.filter_by(username='alice').first()
        u.inhale = bad
        u.exhale = bad
        u.rounds = None
        app_module.db.session.commit()
    resp = auth_client.get('/')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    saved = embedded_json(html, 'SAVED')        # json.loads would fail on None/inf/nan literals
    assert saved == {'inhale': 4.0, 'hold1': 2.0, 'exhale': 6.0, 'hold2': 2.0}
    assert 'None' not in re.search(r'const SAVED = .*', html).group(0)
