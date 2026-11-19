"""Home page in the original plain look: title, welcome line, instruction, inline inputs, buttons, circle."""
import re

import pytest

import i18n
from conftest import register

EN = {'Accept-Language': 'en-US,en;q=0.9'}
PRESET_OPTIONS = [('relax', '放松 4-2-6-2', 'Relax 4-2-6-2'), ('478', '4-7-8 助眠', '4-7-8 Sleep'),
                  ('box', '方块 4-4-4-4', 'Box 4-4-4-4'), ('coherent', '平衡 5-5', 'Coherent 5-5'),
                  ('custom', '自定义', 'Custom')]


def body(html):
    """The page body before the script (what is rendered as markup)."""
    return html[html.index('<body>'):html.index('<script>')]


# ---------------------------------------------------------------- welcome line
@pytest.mark.parametrize('headers,logout', [({}, '登出'), (EN, 'Log out')])
def test_plain_welcome_line(client, headers, logout):
    register(client)
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert f'<p class="user-line">Welcome, alice! <a href="/logout">{logout}</a></p>' in html
    assert 'href="/login"' not in body(html) and 'href="/register"' not in body(html)


def test_welcome_line_escapes_username(client):
    register(client, username='<b>x</b>&"')
    html = client.get('/').get_data(as_text=True)
    assert '<b>x</b>' not in html
    assert ('<p class="user-line">Welcome, &lt;b&gt;x&lt;/b&gt;&amp;&#34;! '
            '<a href="/logout">登出</a></p>') in html


@pytest.mark.parametrize('headers,login,reg', [({}, '登录', '注册'), (EN, 'Log in', 'Sign up')])
def test_logged_out_page_has_login_register_and_no_save(client, headers, login, reg):
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert (f'<p class="user-line"><a href="/login">{login}</a> | '
            f'<a href="/register">{reg}</a></p>') in html
    assert 'id="saveBtn"' not in html and i18n.t('home.save', 'en' if headers else 'zh') not in body(html)
    assert 'Welcome,' not in html and 'href="/logout"' not in html
    assert 'id="startBtn"' in html


def test_logged_in_page_has_save_button(client):
    register(client)
    html = client.get('/').get_data(as_text=True)
    assert '<button type="submit" id="saveBtn">保存设置</button>' in html
    assert 'action="/save_settings"' in html


# ---------------------------------------------------------------- instruction and inputs
@pytest.mark.parametrize('headers,text', [
    ({}, '<p>输入你的 4-2-6-2（吸气-憋气-呼气-憋气）时间，开始训练：</p>'),
    (EN, '<p>Enter your 4-2-6-2 (inhale-hold-exhale-hold) times in seconds, then start:</p>'),
])
def test_old_instruction_line(client, headers, text):
    assert text in client.get('/', headers=headers).get_data(as_text=True)


@pytest.mark.parametrize('headers,labels', [
    ({}, ['吸气', '憋气1', '呼气', '憋气2']),
    (EN, ['Inhale', 'Hold 1', 'Exhale', 'Hold 2']),
])
def test_short_labels_wrap_their_inputs(client, headers, labels):
    html = client.get('/', headers=headers).get_data(as_text=True)
    found = re.findall(r'<label>([^<]+?)\s*<input id="(\w+)" name="\2" type="number"', html)
    assert found == list(zip(labels, ['inhale', 'hold1', 'exhale', 'hold2']))


def test_logged_out_default_values_have_no_trailing_zero(client, monkeypatch):
    import app as app_module
    html = client.get('/').get_data(as_text=True)
    values = dict(re.findall(r'<input id="(\w+)"[^>]*?value="([^"]*)"', html, re.S))
    assert values == {'inhale': '4', 'hold1': '2', 'exhale': '6', 'hold2': '2'}
    monkeypatch.setitem(app_module.SETTING_FIELDS, 'inhale', ('field.inhale', 1.0, 30.0, 4.5))
    html = client.get('/').get_data(as_text=True)
    assert re.search(r'<input id="inhale"[^>]*?value="4\.5"', html, re.S)


@pytest.mark.parametrize('headers,col', [({}, 1), (EN, 2)])
def test_preset_select_with_options_when_logged_in(client, headers, col):
    register(client)
    html = client.get('/', headers=headers).get_data(as_text=True)
    m = re.search(r'<select id="presetSelect" aria-label="([^"]+)">(.*?)</select>', html, re.S)
    assert m and m.group(1) == i18n.t('home.patterns_label', 'en' if headers else 'zh')
    options = re.findall(r'<option value="([^"]+)">([^<]+)</option>', m.group(2))
    assert options == [(o[0], o[col]) for o in PRESET_OPTIONS]
    # On the same row as the four inputs (inside the settings fieldset); no chips or description.
    fieldset = html[html.index('<fieldset class="settings"'):html.index('</fieldset>')]
    assert 'id="presetSelect"' in fieldset and fieldset.count('type="number"') == 4
    assert 'name="pattern"' not in html and 'class="chip"' not in html and 'presetDesc' not in html


@pytest.mark.parametrize('headers', [{}, EN])
def test_logged_out_page_has_no_preset_select(client, headers):
    html = client.get('/', headers=headers).get_data(as_text=True)
    lang = 'en' if headers else 'zh'
    assert 'id="presetSelect"' not in html and '<select' not in body(html)
    assert i18n.t('home.patterns_label', lang) not in body(html)
    assert '<option value=' not in html
    for _, zh, en in PRESET_OPTIONS:
        assert (en if headers else zh) not in body(html)
    # The four timing inputs are still there, inside the fieldset.
    fieldset = html[html.index('<fieldset class="settings"'):html.index('</fieldset>')]
    assert fieldset.count('type="number"') == 4


@pytest.mark.parametrize('user', [False, True])
def test_preset_script_guards_for_missing_select(client, user):
    if user:
        register(client)
    html = client.get('/').get_data(as_text=True)
    script = html[html.index('<script>'):]
    assert 'if (p) FIELDS.forEach((f) => { $(f).value = p[f]; });' in script
    assert 'return "custom";' in script
    # Every use of the select is behind a null check, so guests get no errors.
    assert 'if (presetSelect) {\n    presetSelect.addEventListener("change"' in script
    assert 'if (presetSelect) presetSelect.value = detectPattern();' in script
    # Sent with the recorded session; falls back to the detected pattern.
    assert 'pattern: presetSelect ? presetSelect.value : detectPattern()' in script
    unguarded = [line for line in script.splitlines()
                 if 'presetSelect' in line and 'if (presetSelect)' not in line
                 and 'presetSelect ?' not in line and 'const presetSelect' not in line]
    # Remaining references live inside the guarded block.
    block = script[script.index('if (presetSelect) {'):script.index('\n  }\n', script.index('if (presetSelect) {'))]
    assert all(line in block for line in unguarded), unguarded


# ---------------------------------------------------------------- plain look, nothing else
@pytest.mark.parametrize('user', [False, True])
@pytest.mark.parametrize('headers', [{}, EN])
def test_page_order_and_no_extra_emoji(client, user, headers):
    if user:
        register(client)
    html = client.get('/', headers=headers).get_data(as_text=True)
    order = ['<h1>🌿 ', 'class="user-line"', 'home.instruction', 'id="presetSelect"', 'id="inhale"',
             'id="startBtn"', 'id="circle"', 'id="guideText"', 'class="progressBar"',
             '<details class="breathing-info">']
    order[2] = i18n.t('home.instruction', 'en' if headers else 'zh')
    if not user:
        order.remove('id="presetSelect"')
    positions = [html.index(x) for x in order]
    assert positions == sorted(positions)
    # Only the two leaves of the original page: the title and the principle summary.
    emoji = re.findall(r'[\U0001F300-\U0001FAFF☀-➿⏩-⏺■-◿]', body(html))
    assert emoji == ['🌿', '🌿'], emoji
    assert 'class="card' not in html and '<details class="breathing-info">' in html


@pytest.mark.parametrize('headers', [{}, EN])
def test_sound_and_vibration_live_in_the_collapsed_panel(client, headers):
    html = client.get('/', headers=headers).get_data(as_text=True)
    details = html[html.index('<details class="breathing-info">'):html.index('</details>')]
    assert 'id="soundOpt"' in details and 'id="vibrateOpt"' in details
    assert '<details class="breathing-info" open' not in html


def test_errors_show_as_one_small_line_only_when_present(client):
    html = client.get('/').get_data(as_text=True)
    assert '<p class="error-line" id="formError" role="alert"></p>' in html
    assert '.error-line:empty { display: none; }' in html


def test_small_language_links_not_a_pill(client):
    html = client.get('/').get_data(as_text=True)
    # The page's own styles come after _head.html's shared pill styles and override them.
    page_style = html[html.index('<style>\nbody {'):]
    assert html.index('.lang-switch { display: inline-flex;') < html.index('<style>\nbody {')
    assert '.lang-bar { position: absolute; top: 6px; right: 12px;' in page_style
    assert '.lang-switch { border: none; border-radius: 0; font-size: 12px; }' in page_style
    assert '.lang-switch a[aria-current="true"] { background: none;' in page_style


def test_old_visual_sizes(client):
    html = client.get('/').get_data(as_text=True)
    css = html[html.index('<style>\nbody {'):html.index('</style>', html.index('<style>\nbody {'))]
    for rule in ('background: #0f172a;', 'width: 70px;', 'width: 160px;', 'height: 160px;',
                 'margin: 30px auto;', 'background: radial-gradient(circle, #22c55e, #14532d);',
                 'font-size: 24px;', 'width: 80%;', 'flex-wrap: wrap;', 'background: #22c55e;',
                 'padding: 10px 16px;'):
        assert rule in css, rule
