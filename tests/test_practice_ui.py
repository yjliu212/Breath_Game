"""Practice screen: open-ended loop with no rounds, status line or total progress bar."""
import json
import re

import pytest

import i18n
from conftest import register

EN = {'Accept-Language': 'en-US,en;q=0.9'}
REMOVED_JS_KEYS = ('status_initial', 'status_running', 'status_stopped', 'status_finished_one',
                   'status_finished_other', 'err_rounds_int', 'phase_done')


def embedded_json(html, name):
    m = re.search(r'const %s = (.*?);\n' % name, html)
    assert m, name
    return json.loads(m.group(1))


@pytest.fixture(params=['guest', 'user'])
def home_html(request, client):
    if request.param == 'user':
        register(client)
    return {lang: client.get('/', headers=h).get_data(as_text=True)
            for lang, h in (('zh', {}), ('en', EN))}


def test_no_rounds_input(home_html):
    for html in home_html.values():
        assert 'id="rounds"' not in html and 'name="rounds"' not in html
        assert '轮数' not in html and 'Rounds' not in html
        # The four timing fields remain.
        for name in ('inhale', 'hold1', 'exhale', 'hold2'):
            assert f'id="{name}" name="{name}"' in html
        assert 'rounds' not in embedded_json(html, 'LIMITS')


def test_no_status_line_or_total_progress(home_html):
    for html in home_html.values():
        for gone in ('statusLine', 'status-line', 'totalFill', 'progressBar total', 'session.total'):
            assert gone not in html
        assert not re.search(r'\d+\s*/\s*\d+\s*轮', html)
        assert '剩余' not in html and '{left}' not in html and 'Round ' not in html
        # The single phase progress bar stays.
        assert html.count('class="progressBarFill"') == 1 and 'id="progressFill"' in html


def test_practice_controls_and_options_kept(home_html):
    for html in home_html.values():
        for el in ('id="circle"', 'id="guideText"', 'id="startBtn"',
                   'id="stopBtn" hidden', 'id="soundOpt"',
                   'id="vibrateOpt"', 'id="presetSelect"', 'class="lang-switch"'):
            assert el in html, el
        # The phase text is empty when idle.
        assert '<div id="guideText" aria-live="polite"></div>' in html
    assert '>开始训练</button>' in home_html['zh'] and '>停止</button>' in home_html['zh']
    assert '>Start</button>' in home_html['en'] and '>Stop</button>' in home_html['en']


def test_no_countdown_or_text_inside_circle(home_html):
    for html in home_html.values():
        assert 'countText' not in html and 'class="count"' not in html
        # A plain circle; the phase text sits below it.
        assert '<div class="circle" id="circle"></div>\n\n<div id="guideText"' in html
        assert 'class="phase"' not in html


def test_engine_loops_and_records_completed_cycles_on_stop(home_html):
    html = home_html['zh']
    assert 'finish()' not in html and 'function finish' not in html
    assert 'session.cycles += 1' in html
    assert 'rounds: s.cycles' in html                 # completed cycles are sent as rounds
    assert 'if (LOGGED_IN && s.cycles >= 1) record(s);' in html   # nothing recorded without a full breath
    assert 'const FIELDS = ["inhale", "hold1", "exhale", "hold2"];' in html
    assert '"rounds"' not in html


def test_only_stop_takes_the_start_and_save_spot(home_html):
    for html in home_html.values():
        form = html[html.index('<form id="settingsForm"'):html.index('</form>')]
        for btn in ('id="startBtn"', 'id="stopBtn"'):
            assert btn in form
        assert form.count('<button') == form.count('id="startBtn"') + form.count('id="saveBtn"') + 1
        script = html[html.index('<script>'):]
        assert 'startBtn.hidden = !idle;' in script and 'if (saveBtn) saveBtn.hidden = !idle;' in script
        assert 'stopBtn.hidden = idle;' in script
        assert 'stopBtn.addEventListener("click", stop);' in script
        # Same plain green style for every button: no secondary/danger variants.
        assert 'class="secondary"' not in html and 'class="danger"' not in html
    assert '<button type="button" id="stopBtn" hidden>停止</button>' in home_html['zh']
    assert '<button type="button" id="stopBtn" hidden>Stop</button>' in home_html['en']


def test_no_pause_or_resume_remains(home_html):
    for lang, html in home_html.items():
        assert 'pauseBtn' not in html and 'togglePause' not in html and 'pausedAt' not in html
        assert '"paused"' not in html and 'keydown' not in html
        msg = embedded_json(html, 'MSG')
        for key in ('btn_pause', 'btn_resume', 'phase_paused'):
            assert key not in msg
    for word in ('暂停', '已暂停', '继续'):
        assert word not in home_html['zh']
    for word in ('Pause', 'Resume', 'Paused'):
        assert word not in home_html['en']
    for key in ('js.btn_pause', 'js.btn_resume', 'js.phase_paused'):
        assert key not in i18n.MESSAGES


def test_removed_js_messages_are_gone(home_html):
    for lang, html in home_html.items():
        msg = embedded_json(html, 'MSG')
        for key in REMOVED_JS_KEYS:
            assert key not in msg
        assert msg == i18n.js_messages(lang)
    assert '未完成不计入' not in home_html['zh']
    assert 'not recorded' not in home_html['en']


def test_every_msg_reference_in_template_exists(home_html):
    html = home_html['en']
    script = html[html.index('<script>'):]
    used = set(re.findall(r'MSG\.(\w+)', script))
    assert used and used <= set(embedded_json(html, 'MSG'))
