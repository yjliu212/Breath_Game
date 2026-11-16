"""Practice record API, stats and streaks, plus static endpoints."""
from datetime import date, datetime, timedelta, timezone

import pytest

import app as app_module

TODAY = datetime.now(timezone.utc).date()
GOOD = {'inhale': 4, 'hold1': 7, 'exhale': 8, 'hold2': 0, 'rounds': 2,
        'pattern': '478', 'local_date': TODAY.isoformat()}


def test_record_requires_login(client):
    resp = client.post('/api/sessions', json=GOOD)
    assert resp.status_code == 401
    assert resp.get_json()['ok'] is False
    assert client.get('/api/stats').status_code == 401


def test_record_valid_session_updates_stats(app, auth_client):
    resp = auth_client.post('/api/sessions', json=GOOD)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['ok'] is True
    assert data['duration_seconds'] == 38.0            # (4+7+8+0) * 2, computed server-side
    assert data['stats'] == {'sessions': 1, 'minutes': 0.6, 'streak': 1}
    assert auth_client.get('/api/stats').get_json() == data['stats']
    html = auth_client.get('/').get_data(as_text=True)
    assert '>你已经在这里静下来 1 次，共 0.6 分钟。</p>' in html
    with app.app_context():
        row = app_module.PracticeSession.query.one()
        assert (row.pattern, row.rounds, row.local_date) == ('478', 2, TODAY)


def test_client_supplied_duration_is_ignored(auth_client):
    resp = auth_client.post('/api/sessions', json=dict(GOOD, duration_seconds=99999))
    assert resp.get_json()['duration_seconds'] == 38.0


@pytest.mark.parametrize('override', [
    {'inhale': 0}, {'inhale': -1}, {'exhale': 31}, {'hold1': 'abc'}, {'hold2': None},
    {'rounds': 0}, {'rounds': None}, {'rounds': 7201}, {'rounds': 1.5}, {'rounds': True},
    {'pattern': '<script>'}, {'local_date': 'yesterday'}, {'local_date': '2020-01-01'},
    {'local_date': (TODAY + timedelta(days=5)).isoformat()},
])
def test_record_rejects_invalid_data(app, auth_client, override):
    resp = auth_client.post('/api/sessions', json=dict(GOOD, **override))
    assert resp.status_code == 400
    assert resp.get_json()['ok'] is False
    with app.app_context():
        assert app_module.PracticeSession.query.count() == 0


def test_record_long_open_ended_session(app, auth_client):
    # Practice loops until Stop, so more than the old 50-round limit is fine.
    resp = auth_client.post('/api/sessions', json=dict(GOOD, rounds=120))
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()['duration_seconds'] == 19 * 120
    with app.app_context():
        assert app_module.PracticeSession.query.one().rounds == 120


def test_record_rejects_implausibly_long_session(app, auth_client):
    # 19 s cycle * 800 cycles > 4 h
    resp = auth_client.post('/api/sessions', json=dict(GOOD, rounds=800))
    assert resp.status_code == 400
    assert resp.get_json()['error'] == '单次练习时长超出上限。'
    with app.app_context():
        assert app_module.PracticeSession.query.count() == 0


def test_record_rejects_nan_and_inf(app, auth_client):
    for literal in ('NaN', 'Infinity', '-Infinity'):
        body = '{"inhale": %s, "hold1": 1, "exhale": 4, "hold2": 1, "rounds": 1, "local_date": "%s"}' % (
            literal, TODAY.isoformat())
        resp = auth_client.post('/api/sessions', data=body, content_type='application/json')
        assert resp.status_code == 400


def test_record_rejects_non_json(auth_client):
    assert auth_client.post('/api/sessions', data=GOOD).status_code == 400
    assert auth_client.post('/api/sessions', data='[1,2]', content_type='application/json').status_code == 400
    assert auth_client.post('/api/sessions', data='{bad', content_type='application/json').status_code == 400


def test_record_too_fast_is_rejected(auth_client):
    assert auth_client.post('/api/sessions', json=GOOD).status_code == 201
    # Another 38 s session can't have finished a moment later.
    resp = auth_client.post('/api/sessions', json=GOOD)
    assert resp.status_code == 429
    assert auth_client.get('/api/stats').get_json()['sessions'] == 1


def add_session(user_id, day, seconds=60.0):
    app_module.db.session.add(app_module.PracticeSession(
        user_id=user_id, local_date=day, duration_seconds=seconds, rounds=1,
        inhale=4, hold1=2, exhale=6, hold2=2, pattern='relax',
        completed_at=datetime(day.year, day.month, day.day, 12)))
    app_module.db.session.commit()


def test_stats_and_streak(app, auth_client):
    today = date(2026, 11, 15)
    with app.app_context():
        uid = app_module.User.query.filter_by(username='alice').one().id
        assert app_module.compute_stats(uid, today) == {'sessions': 0, 'minutes': 0.0, 'streak': 0}

        for d in (today, today, today - timedelta(days=1), today - timedelta(days=2),
                  today - timedelta(days=4)):          # gap on day -3
            add_session(uid, d, 90)
        assert app_module.compute_stats(uid, today) == {'sessions': 5, 'minutes': 7.5, 'streak': 3}
        # Last practice yesterday: streak is still alive.
        assert app_module.compute_stats(uid, today + timedelta(days=1))['streak'] == 3
        # Two days without practice: streak broken.
        assert app_module.compute_stats(uid, today + timedelta(days=2))['streak'] == 0


def test_stats_are_per_user(app, client):
    from conftest import register
    register(client, 'bob', 'secret123')
    with app.app_context():
        bob = app_module.User.query.filter_by(username='bob').one().id
        add_session(bob, TODAY)
    client.get('/logout')
    register(client, 'carol', 'secret123')
    assert client.get('/api/stats').get_json()['sessions'] == 0


def test_favicon(client):
    resp = client.get('/favicon.ico')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/svg+xml'
    assert b'<svg' in resp.data
    resp.close()
    static = client.get('/static/favicon.svg')
    assert static.status_code == 200
    static.close()


def test_robots(client):
    resp = client.get('/robots.txt')
    assert resp.status_code == 200
    assert resp.mimetype == 'text/plain'
    assert b'User-agent: *' in resp.data
    resp.close()
