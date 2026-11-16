"""Logged-in warmth: greeting, calm line, quiet stats sentence, anonymous "breathing together"."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

import app as app_module
import i18n
from conftest import register, login

EN = {'Accept-Language': 'en-US,en;q=0.9'}
TODAY = datetime.now(timezone.utc).date()
GOOD = {'inhale': 4, 'hold1': 7, 'exhale': 8, 'hold2': 0, 'rounds': 2,
        'pattern': '478', 'local_date': TODAY.isoformat()}
# Markup that only logged-in pages may contain.
LOGGED_IN_MARKERS = ('id="welcome"', 'id="greeting"', 'id="calmLine"', 'id="statsLine"',
                     'id="together"', 'id="afterglow"', 'class="afterglow"')
LOGGED_IN_TEXT = ('你好，', 'Hello, ', '谢谢你给自己这一刻', 'Thank you for taking this moment',
                  '一起呼吸', 'breathed here today', '静下来', 'paused here')


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_user(name):
    user = app_module.User(username=name)
    user.set_password('secret123')
    app_module.db.session.add(user)
    app_module.db.session.commit()
    return user.id


def add_session(user_id, completed_at):
    app_module.db.session.add(app_module.PracticeSession(
        user_id=user_id, completed_at=completed_at, local_date=completed_at.date(),
        duration_seconds=60, rounds=5, inhale=4, hold1=2, exhale=6, hold2=2, pattern='relax'))
    app_module.db.session.commit()


def embedded_json(html, name):
    m = re.search(r'const %s = (.*?);(?:\n| +//)' % name, html)
    assert m, name
    return json.loads(m.group(1))


def together_line(html):
    m = re.search(r'<p class="quiet" id="together">([^<]*)</p>', html)
    return m and m.group(1)


# ---------------------------------------------------------------- count_recent_breathers
def test_count_empty_db(app):
    with app.app_context():
        assert app_module.count_recent_breathers() == 0


def test_count_is_distinct_users(app):
    with app.app_context():
        now = now_utc()
        a, b = make_user('a1'), make_user('b1')
        for minutes in (1, 5, 30):
            add_session(a, now - timedelta(minutes=minutes))
        assert app_module.count_recent_breathers(now) == 1
        add_session(b, now - timedelta(hours=2))
        assert app_module.count_recent_breathers(now) == 2


def test_count_uses_24_hour_window(app):
    with app.app_context():
        now = datetime(2026, 11, 16, 12, 0, 0)
        old, recent, edge, future = (make_user(n) for n in ('old', 'recent', 'edge', 'future'))
        add_session(old, now - timedelta(hours=24, seconds=1))
        add_session(edge, now - timedelta(hours=24))           # exactly 24 h ago: outside
        add_session(recent, now - timedelta(hours=23, minutes=59))
        add_session(future, now + timedelta(minutes=1))        # after `now`: not counted
        assert app_module.count_recent_breathers(now) == 1
        # Aware datetimes are converted to UTC first.
        aware = now.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        assert app_module.count_recent_breathers(aware) == 1
        # A day later nobody is in the window.
        assert app_module.count_recent_breathers(now + timedelta(days=2)) == 0


# ---------------------------------------------------------------- logged out
@pytest.mark.parametrize('headers', [{}, EN])
def test_logged_out_home_has_no_logged_in_markup(app, client, headers):
    with app.app_context():
        now = now_utc()
        for name in ('p1', 'p2', 'p3'):
            add_session(make_user(name), now - timedelta(minutes=5))
    html = client.get('/', headers=headers).get_data(as_text=True)
    for marker in LOGGED_IN_MARKERS + LOGGED_IN_TEXT:
        assert marker not in html, marker
    assert 'class="user-bar"' in html                 # the original guest bar is unchanged
    assert embedded_json(html, 'WARM') is None
    assert embedded_json(html, 'MSG') == i18n.js_messages('en' if headers else 'zh')


# ---------------------------------------------------------------- logged in
def test_greeting_escapes_username(client):
    register(client, username='<b>x</b>')
    html = client.get('/').get_data(as_text=True)
    assert '<b>x</b>' not in html
    assert '<span id="greeting" data-name="&lt;b&gt;x&lt;/b&gt;">你好，&lt;b&gt;x&lt;/b&gt;</span>' in html
    assert 'href="/logout"' in html
    # The JS swaps the greeting via textContent, never innerHTML.
    assert 'greetEl.textContent = fmtMsg(' in html and 'innerHTML' not in html


@pytest.mark.parametrize('headers,lang', [({}, 'zh'), (EN, 'en')])
def test_greeting_and_calm_line_in_both_languages(client, headers, lang):
    register(client)
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert i18n.t('warm.greet_default', lang, name='alice') in html
    assert i18n.t('auth.logout', lang) in html
    calm = i18n.t(app_module.calm_key(), lang).replace("'", '&#39;')
    assert f'<p class="quiet" id="calmLine">{calm}</p>' in html
    warm = embedded_json(html, 'WARM')
    assert warm == i18n.warm_messages(lang)
    assert '{name}' in warm['greet_evening'] and '{n}' in warm['not_alone']


def test_calm_line_is_deterministic_by_date():
    day = date(2026, 11, 16)
    assert app_module.calm_key(day) == app_module.calm_key(day)
    week = {app_module.calm_key(day + timedelta(days=i)) for i in range(7)}
    assert week == set(i18n.CALM_KEYS) and len(i18n.CALM_KEYS) == 7


def test_together_hidden_when_fewer_than_two(app, client):
    register(client)
    assert 'id="together"' not in client.get('/').get_data(as_text=True)   # N == 0
    assert client.post('/api/sessions', json=GOOD).status_code == 201
    assert 'id="together"' not in client.get('/').get_data(as_text=True)   # N == 1 (just me)
    with app.app_context():                                                 # old sessions don't count
        add_session(make_user('long_ago'), now_utc() - timedelta(days=3))
    assert 'id="together"' not in client.get('/').get_data(as_text=True)


@pytest.mark.parametrize('headers,before,after', [
    ({}, '今天有 2 位朋友在这里一起呼吸', '今天有 3 位朋友在这里一起呼吸'),
    (EN, '2 people breathed here today', '3 people breathed here today'),
])
def test_together_shown_with_real_count(app, client, headers, before, after):
    with app.app_context():
        now = now_utc()
        a, b = make_user('friend_a'), make_user('friend_b')
        add_session(a, now - timedelta(minutes=10))     # two sessions, still one person
        add_session(a, now - timedelta(minutes=20))
        add_session(b, now - timedelta(hours=3))
    register(client)
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert together_line(html) == before                # two others, I haven't practised yet
    assert client.post('/api/sessions', json=GOOD).status_code == 201
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert together_line(html) == after
    # Never anyone else's name.
    assert 'friend_a' not in html and 'friend_b' not in html


# ---------------------------------------------------------------- stats sentence
@pytest.mark.parametrize('headers,expected', [
    ({}, '你已经在这里静下来 1 次，共 0.6 分钟。'),
    (EN, 'You&#39;ve paused here 1 time, 0.6 minutes in all.'),
])
def test_stats_sentence_hidden_until_first_session(client, headers, expected):
    register(client)
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert '<p class="quiet" id="statsLine" hidden></p>' in html
    assert '静下来' not in html.split('<script>')[0] and 'paused here' not in html.split('<script>')[0]
    assert client.post('/api/sessions', json=GOOD).status_code == 201
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert f'<p class="quiet" id="statsLine">{expected}</p>' in html


def test_stats_sentence_plural_and_whole_minutes(app, client):
    register(client)
    with app.app_context():
        uid = app_module.User.query.filter_by(username='alice').one().id
        add_session(uid, now_utc() - timedelta(hours=5))
        add_session(uid, now_utc() - timedelta(hours=4))
    html = client.get('/', headers=EN).get_data(as_text=True)
    assert 'You&#39;ve paused here 2 times, 2 minutes in all.' in html


def test_no_streak_or_stat_grid_on_page(client):
    register(client)
    client.post('/api/sessions', json=GOOD)
    for headers in ({}, EN):
        html = client.get('/', headers=headers).get_data(as_text=True)
        for gone in ('class="card stats"', 'class="stat"', 'statSessions', 'statMinutes', 'statStreak',
                     '连续天数', 'Day streak', 'streak'):
            assert gone not in html, gone


def test_stats_api_unchanged(client):
    register(client)
    client.post('/api/sessions', json=GOOD)
    assert client.get('/api/stats').get_json() == {'sessions': 1, 'minutes': 0.6, 'streak': 1}


# ---------------------------------------------------------------- /api/sessions + thank-you
def test_record_returns_together(app, client):
    register(client)
    data = client.post('/api/sessions', json=GOOD).get_json()
    assert data['ok'] is True and data['together'] == 1
    assert data['stats']['sessions'] == 1
    with app.app_context():
        add_session(make_user('other'), now_utc() - timedelta(minutes=30))
    client.get('/logout')
    register(client, username='bob')
    assert client.post('/api/sessions', json=GOOD).get_json()['together'] == 3


def test_thank_you_region_is_polite_live_and_wired(client):
    register(client)
    html = client.get('/').get_data(as_text=True)
    assert '<div class="afterglow" id="afterglow" aria-live="polite"></div>' in html
    script = html[html.index('<script>'):]
    assert 'showAfterglow(res.data.together)' in script
    assert 'updateStatsLine(res.data.stats)' in script
    assert '(Number(together) || 0) - 1' in script and 'if (others >= 1)' in script
    used = set(re.findall(r'WARM\.(\w+)', script))
    assert used and used <= set(embedded_json(html, 'WARM'))


@pytest.mark.parametrize('lang', ['zh', 'en'])
def test_warm_strings_have_both_languages(lang):
    for key in [k for k in i18n.MESSAGES if k.startswith('warm.')]:
        assert i18n.t(key, lang).strip()
    assert i18n.warm_messages(lang).keys() == i18n.warm_messages('zh').keys()
