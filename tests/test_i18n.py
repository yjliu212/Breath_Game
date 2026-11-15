"""Chinese / English localisation: language selection, switching and translated output."""
import json
import re
import string
from datetime import datetime, timezone

import pytest

import i18n
from conftest import register, login

EN = {'Accept-Language': 'en-US,en;q=0.9'}
ZH = {'Accept-Language': 'zh-CN,zh;q=0.9'}
CJK = re.compile(r'[一-鿿　-〿＀-￯]')
# Chinese that is intentionally on English pages: the language switch itself.
ALLOWED_ON_EN = ('切换到中文 (Switch to Chinese)', 'Language / 语言', '>中文<')
TODAY = datetime.now(timezone.utc).date().isoformat()
VALID = {'inhale': '4', 'hold1': '2', 'exhale': '6', 'hold2': '2'}


def html_lang(html):
    return re.search(r'<html lang="([^"]+)">', html).group(1)


def embedded_json(html, name):
    m = re.search(r'const %s = (.*?);\n' % name, html)
    assert m, name
    return json.loads(m.group(1))


def strip_allowed(html):
    for s in ALLOWED_ON_EN:
        html = html.replace(s, '')
    return html


# ---------------------------------------------------------------- dictionary
def placeholders(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


@pytest.mark.parametrize('key', sorted(i18n.MESSAGES))
def test_every_message_has_both_languages(key):
    entry = i18n.MESSAGES[key]
    assert set(entry) == set(i18n.LANGS)
    assert all(entry[lang].strip() for lang in i18n.LANGS)
    assert placeholders(entry['zh']) == placeholders(entry['en'])
    assert not CJK.search(entry['en']) or key.startswith('lang.')


def test_js_messages_have_same_keys():
    assert i18n.js_messages('zh').keys() == i18n.js_messages('en').keys()


# ---------------------------------------------------------------- language selection
@pytest.mark.parametrize('headers,expected', [
    ({}, 'zh-CN'),                                        # no preference -> Chinese
    (EN, 'en'),
    ({'Accept-Language': 'en'}, 'en'),
    ({'Accept-Language': 'en-GB'}, 'en'),
    (ZH, 'zh-CN'),
    ({'Accept-Language': 'zh-TW'}, 'zh-CN'),
    ({'Accept-Language': 'zh;q=0.9, en;q=0.5'}, 'zh-CN'),
    ({'Accept-Language': 'en;q=0.9, zh;q=0.5'}, 'en'),
    ({'Accept-Language': 'fr-FR, de'}, 'zh-CN'),          # unsupported -> Chinese
])
def test_language_from_accept_language(client, headers, expected):
    assert html_lang(client.get('/', headers=headers).get_data(as_text=True)) == expected


def test_default_home_is_chinese(client):
    html = client.get('/').get_data(as_text=True)
    assert html_lang(html) == 'zh-CN'
    assert '<title>呼吸训练小游戏</title>' in html
    assert '▶ 开始' in html and '>准备<' in html
    assert 'og:locale" content="zh_CN"' in html
    assert embedded_json(html, 'MSG')['phase_inhale'] == '吸气'


def test_english_home_has_no_leftover_chinese(client):
    html = client.get('/', headers=EN).get_data(as_text=True)
    assert html_lang(html) == 'en'
    assert '<title>Breath Game</title>' in html
    assert '<h1>🌿 Breath Game</h1>' in html
    assert 'og:site_name" content="Breath Game"' in html
    assert 'og:title" content="Breath Game"' in html
    assert 'Breathing Practice' not in html                      # old brand name fully gone
    assert '▶ Start' in html and 'Relax 4-2-6-2' in html and 'Hold after inhale (sec)' in html
    assert 'og:locale" content="en_US"' in html
    assert 'How breathing practice works' in html
    assert '<strong>Why hold your breath?</strong>' in html      # _html keys keep their markup
    msg = embedded_json(html, 'MSG')
    assert msg['phase_inhale'] == 'Inhale' and msg['btn_resume'] == '▶ Resume'
    limits = embedded_json(html, 'LIMITS')
    assert limits['hold2']['label'] == 'Hold after exhale' and 'rounds' not in limits
    leftover = CJK.findall(strip_allowed(html))
    assert not leftover, ''.join(leftover)


def test_english_logged_in_home_has_no_leftover_chinese(client):
    register(client, headers=EN)
    html = client.get('/', headers=EN).get_data(as_text=True)
    assert 'Welcome, alice!' in html and 'Log out' in html
    assert 'Registration successful — welcome!' in html
    assert 'Sessions' in html and 'Total minutes' in html and 'Day streak' in html
    assert 'Save settings' in html
    leftover = CJK.findall(strip_allowed(html))
    assert not leftover, ''.join(leftover)


def test_cookie_overrides_accept_language(client):
    client.set_cookie('lang', 'zh')
    assert html_lang(client.get('/', headers=EN).get_data(as_text=True)) == 'zh-CN'
    client.set_cookie('lang', 'en')
    assert html_lang(client.get('/', headers=ZH).get_data(as_text=True)) == 'en'


def test_invalid_cookie_is_ignored(client):
    client.set_cookie('lang', 'xx')
    assert html_lang(client.get('/', headers=EN).get_data(as_text=True)) == 'en'
    assert html_lang(client.get('/').get_data(as_text=True)) == 'zh-CN'


def test_responses_vary_on_language(client):
    vary = client.get('/').headers['Vary']
    assert 'Accept-Language' in vary and 'Cookie' in vary


# ---------------------------------------------------------------- switching
def test_switch_sets_cookie_and_redirects_back(client):
    resp = client.get('/lang/en?next=/login', headers=ZH)
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/login'
    cookie = resp.headers['Set-Cookie']
    assert cookie.startswith('lang=en;')
    assert 'Max-Age=31536000' in cookie and 'SameSite=Lax' in cookie and 'Path=/' in cookie
    assert 'HttpOnly' in cookie
    # Later requests use the saved choice even though the browser prefers Chinese.
    html = client.get('/login', headers=ZH).get_data(as_text=True)
    assert html_lang(html) == 'en' and '<h1>Log in</h1>' in html
    # And back to Chinese.
    client.get('/lang/zh?next=/', headers=EN)
    assert client.get_cookie('lang').value == 'zh'
    assert html_lang(client.get('/', headers=EN).get_data(as_text=True)) == 'zh-CN'


def test_switch_is_case_insensitive_and_rejects_unknown(client):
    assert client.get('/lang/EN').headers['Set-Cookie'].startswith('lang=en;')
    assert client.get('/lang/fr').status_code == 404


@pytest.mark.parametrize('nxt,expected', [
    (None, '/'),
    ('/register', '/register'),
    ('/?a=1', '/?a=1'),
    ('https://evil.example/', '/'),
    ('//evil.example/', '/'),
    ('/\\evil.example', '/'),
    ('javascript:alert(1)', '/'),
    ('login', '/'),
])
def test_switch_only_redirects_to_local_paths(client, nxt, expected):
    resp = client.get('/lang/en', query_string={'next': nxt} if nxt is not None else None)
    assert resp.status_code == 302
    assert resp.headers['Location'] == expected


@pytest.mark.parametrize('path', ['/', '/login', '/register'])
@pytest.mark.parametrize('headers,current', [({}, 'zh'), (EN, 'en')])
def test_switch_control_on_every_page(client, path, headers, current):
    html = client.get(path, headers=headers).get_data(as_text=True)
    assert 'class="lang-switch"' in html
    assert f'href="/lang/zh?next={path}"' in html and f'href="/lang/en?next={path}"' in html
    active = re.findall(r'<a href="/lang/(\w+)[^>]*aria-current="true"', html)
    assert active == [current]


def test_switch_control_keeps_logged_in_session(client):
    register(client)
    client.get('/lang/en?next=/')
    assert 'Welcome, alice!' in client.get('/').get_data(as_text=True)


# ---------------------------------------------------------------- auth pages
@pytest.mark.parametrize('path,zh_words,en_words', [
    ('/login', ['<title>登录 - 呼吸训练小游戏</title>', '<h1>登录</h1>', '>用户名</label>', '>密码</label>',
                'value="登录"', '还没有账号？<a', '← 返回首页'],
     ['<title>Log in - Breath Game</title>', '<h1>Log in</h1>', '>Username</label>', '>Password</label>',
      'value="Log in"', "Don&#39;t have an account? <a", '← Back to home']),
    ('/register', ['<title>注册 - 呼吸训练小游戏</title>', '<h1>注册</h1>', 'value="注册"', '已有账号？<a'],
     ['<title>Sign up - Breath Game</title>', '<h1>Sign up</h1>', 'value="Sign up"',
      'Already have an account? <a']),
])
def test_auth_pages_in_both_languages(client, path, zh_words, en_words):
    zh = client.get(path, headers=ZH).get_data(as_text=True)
    en = client.get(path, headers=EN).get_data(as_text=True)
    assert html_lang(zh) == 'zh-CN' and html_lang(en) == 'en'
    for w in zh_words:
        assert w in zh
    for w in en_words:
        assert w in en
    leftover = CJK.findall(strip_allowed(en))
    assert not leftover, ''.join(leftover)


# ---------------------------------------------------------------- English flash / validation
def test_english_form_validation(client):
    html = register(client, password='123', headers=EN).get_data(as_text=True)
    assert 'Password must be at least 6 characters' in html
    html = register(client, username='a', headers=EN).get_data(as_text=True)
    assert 'Username must be 2–150 characters' in html
    html = client.post('/login', data={'username': '', 'password': ''}, headers=EN).get_data(as_text=True)
    assert 'Please enter a username' in html and 'Please enter a password' in html


def test_same_form_class_switches_language_per_request(client):
    zh = register(client, password='123', headers=ZH).get_data(as_text=True)
    en = register(client, password='123', headers=EN).get_data(as_text=True)
    assert '密码至少 6 位' in zh and 'Password must be' not in zh
    assert 'Password must be at least 6 characters' in en and '密码至少' not in en


def test_english_auth_flashes(client):
    register(client)
    client.get('/logout')
    assert 'That username is already taken' in register(client, headers=EN).get_data(as_text=True)
    assert 'Incorrect username or password' in login(client, password='nope-nope', headers=EN).get_data(as_text=True)


def test_english_login_required_flash(client):
    resp = client.post('/save_settings', data=VALID, headers=EN, follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert 'Please log in first.' in html
    assert '请先登录' not in html


def test_chinese_login_required_flash(client):
    html = client.post('/save_settings', data=VALID, follow_redirects=True).get_data(as_text=True)
    assert '请先登录。' in html


def test_english_settings_flashes(client):
    register(client)
    client.set_cookie('lang', 'en')
    html = client.post('/save_settings', data=VALID, follow_redirects=True).get_data(as_text=True)
    assert 'Settings saved!' in html


@pytest.mark.parametrize('field,value,message', [
    ('inhale', '', 'Inhale is required.'),
    ('hold1', 'abc', 'Hold after inhale must be a number.'),
    ('hold2', 'nan', 'Hold after exhale must be a valid number.'),
    ('hold2', '-0.5', 'Hold after exhale cannot be negative.'),
    ('exhale', '31', 'Exhale must be between 1 and 30 seconds.'),
])
def test_english_settings_validation(client, field, value, message):
    register(client)
    client.set_cookie('lang', 'en')
    html = client.post('/save_settings', data=dict(VALID, **{field: value}),
                       follow_redirects=True).get_data(as_text=True)
    assert message in html
    assert 'Settings were not saved. Please fix the errors and try again.' in html
    assert 'Settings saved!' not in html


# ---------------------------------------------------------------- API errors
def test_api_errors_follow_language(client):
    assert client.post('/api/sessions', json={}).get_json()['error'] == '请先登录。'
    assert client.post('/api/sessions', json={}, headers=EN).get_json()['error'] == 'Please log in first.'
    assert client.get('/api/stats', headers=EN).get_json()['error'] == 'Please log in first.'
    register(client)
    client.set_cookie('lang', 'en')
    assert client.post('/api/sessions', data='x', content_type='text/plain').get_json()['error'] == \
        'Invalid request format.'
    body = {'inhale': 4, 'hold1': 7, 'exhale': 8, 'hold2': 0, 'rounds': 2,
            'pattern': 'nope', 'local_date': 'bad'}
    err = client.post('/api/sessions', json=body).get_json()['error']
    assert 'Unknown breathing pattern.' in err and 'Invalid date format.' in err
    body.update(pattern='478', local_date=TODAY)
    assert client.post('/api/sessions', json=body).status_code == 201
    resp = client.post('/api/sessions', json=body)
    assert resp.status_code == 429
    assert resp.get_json()['error'] == 'Sessions are being recorded too quickly.'


# ---------------------------------------------------------------- vibration option untouched
@pytest.mark.parametrize('headers', [{}, EN])
def test_vibration_feature_detection_kept(client, headers):
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert 'id="vibrateOpt"' in html
    assert 'if (typeof navigator.vibrate !== "function")' in html
    assert 'vibrateOpt.parentElement.hidden = true;' in html
    assert 'loadOpt(vibrateOpt, "breath.vibrate");' in html
