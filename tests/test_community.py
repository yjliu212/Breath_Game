"""Anonymous "breathing together" count and stats: kept in the backend / API, never shown on the page."""
import re
from datetime import datetime, timedelta, timezone

import pytest

import app as app_module
import i18n
from conftest import register

EN = {'Accept-Language': 'en-US,en;q=0.9'}
TODAY = datetime.now(timezone.utc).date()
GOOD = {'inhale': 4, 'hold1': 7, 'exhale': 8, 'hold2': 0, 'rounds': 2,
        'pattern': '478', 'local_date': TODAY.isoformat()}
# Markup and text of the removed welcome / stats / together / thank-you UI.
REMOVED_MARKERS = ('id="welcome"', 'id="greeting"', 'id="calmLine"', 'id="statsLine"',
                   'id="together"', 'id="afterglow"', 'class="afterglow"', 'class="quiet"',
                   'id="doneMsg"', 'const WARM', 'WARM.', 'showAfterglow', 'updateStatsLine',
                   'res.data.together', 'res.data.stats')
REMOVED_TEXT = ('你好，', 'Hello, ', '早上好', 'Good morning', '谢谢你给自己这一刻', 'Thank you for taking this moment',
                '位朋友', '一起呼吸', 'breathed here today', '静下来', 'paused here', '分钟', 'minutes in all',
                '本次练习已结束', 'Session ended', '已记录', 'Saved ✔', '连续天数', 'Day streak', 'streak')


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


# ---------------------------------------------------------------- API keeps stats and together
def test_stats_api_unchanged(client):
    register(client)
    client.post('/api/sessions', json=GOOD)
    assert client.get('/api/stats').get_json() == {'sessions': 1, 'minutes': 0.6, 'streak': 1}


def test_record_returns_together_and_stats(app, client):
    register(client)
    data = client.post('/api/sessions', json=GOOD).get_json()
    assert data['ok'] is True and data['together'] == 1
    assert data['stats'] == {'sessions': 1, 'minutes': 0.6, 'streak': 1}
    with app.app_context():
        add_session(make_user('other'), now_utc() - timedelta(minutes=30))
    client.get('/logout')
    register(client, username='bob')
    assert client.post('/api/sessions', json=GOOD).get_json()['together'] == 3


# ---------------------------------------------------------------- nothing of it on the page
def assert_plain_page(html):
    for marker in REMOVED_MARKERS + REMOVED_TEXT:
        assert marker not in html, marker


@pytest.mark.parametrize('headers', [{}, EN])
def test_logged_in_page_has_no_stats_or_together_even_with_data(app, client, headers):
    with app.app_context():
        now = now_utc()
        for name in ('friend_a', 'friend_b', 'friend_c'):
            add_session(make_user(name), now - timedelta(minutes=5))
    register(client)
    for _ in range(2):
        assert client.post('/api/sessions', json=GOOD).status_code in (201, 429)
    with app.app_context():
        uid = app_module.User.query.filter_by(username='alice').one().id
        add_session(uid, now_utc() - timedelta(days=1))
        assert app_module.count_recent_breathers() >= 4
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert_plain_page(html)
    assert 'friend_a' not in html


@pytest.mark.parametrize('headers', [{}, EN])
def test_logged_out_page_has_no_stats_or_together_even_with_data(app, client, headers):
    with app.app_context():
        now = now_utc()
        for name in ('p1', 'p2', 'p3'):
            add_session(make_user(name), now - timedelta(minutes=5))
    html = client.get('/', headers=headers).get_data(as_text=True)
    assert_plain_page(html)


def test_record_is_silent_and_only_failures_are_shown(client):
    register(client)
    html = client.get('/').get_data(as_text=True)
    script = html[html.index('<script>'):]
    assert 'if (!(res.ok && res.data.ok)) fail(res.data.error || MSG.unknown_error);' in script
    assert '.catch(() => fail(MSG.network_error));' in script
    assert 'innerHTML' not in script
    # The only place the outcome is written is the (empty, hidden-when-empty) error line.
    assert '<p class="error-line" id="recordError" role="alert"></p>' in html
    assert re.findall(r'recordError\.textContent = ([^;]+);', script) == ['""', 'fmtMsg(MSG.record_failed, { error: error })']


def test_removed_i18n_keys_are_gone():
    for key in i18n.MESSAGES:
        assert not key.startswith('warm.'), key
    for key in ('js.done', 'js.done_login_hint', 'js.recorded', 'js.phase_ready', 'js.btn_start',
                'js.btn_stop', 'js.preset_relax', 'js.preset_custom', 'home.login_hint', 'home.practice_label', 'field.seconds_suffix'):
        assert key not in i18n.MESSAGES, key
    assert not hasattr(i18n, 'warm_messages') and not hasattr(i18n, 'CALM_KEYS')
    assert not hasattr(app_module, 'calm_key') and not hasattr(app_module, 'format_minutes')
