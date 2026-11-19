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
                   'id="vibrateOpt"', 'class="lang-switch"'):
            assert el in html, el
        # The phase text is empty when idle.
        assert '<div id="guideText" aria-live="polite"></div>' in html
    assert '>开始训练</button>' in home_html['zh'] and '>停止训练</button>' in home_html['zh']
    assert '>Start Training</button>' in home_html['en'] and '>Stop Training</button>' in home_html['en']


def test_no_countdown_or_text_inside_circle(home_html):
    for html in home_html.values():
        assert 'countText' not in html and 'class="count"' not in html
        # A plain circle; the phase text sits below it.
        # (It is also the orb-style switch, so it carries button semantics; see test_orb_styles.py.)
        assert re.search(r'<div class="circle" id="circle"[^>]*></div>\n\n<div id="guideText"', html)
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
    assert '<button type="button" id="stopBtn" hidden>停止训练</button>' in home_html['zh']
    assert '<button type="button" id="stopBtn" hidden>Stop Training</button>' in home_html['en']


@pytest.mark.parametrize('lang,start,stop', [('zh', '开始训练', '停止训练'),
                                             ('en', 'Start Training', 'Stop Training')])
def test_start_and_stop_labels(home_html, lang, start, stop):
    html = home_html[lang]
    assert i18n.t('home.start', lang) == start and i18n.t('home.stop', lang) == stop
    assert f'<button type="button" id="startBtn">{start}</button>' in html
    assert f'<button type="button" id="stopBtn" hidden>{stop}</button>' in html
    if lang == 'en':
        assert '>Start</button>' not in html and '>Stop</button>' not in html
    else:
        assert '>停止</button>' not in html


def test_start_and_stop_share_one_cell_with_the_plain_button_style(home_html):
    for html in home_html.values():
        start = html.index('<style>\nbody {')
        css = html[start:html.index('</style>', start)]
        # The one button rule (also used by Save) gives the original look.
        m = re.search(r'\nbutton \{([^}]*)\}', css)
        assert m, 'base button rule missing'
        for decl in ('padding: 10px 16px;', 'font-size: 16px;', 'border-radius: 8px;'):
            assert decl in m.group(1), decl
        # No rule sizes Start/Stop on their own: no forced width, padding or font.
        assert '#startBtn' not in css and '#stopBtn' not in css
        assert 'min-width: 10em' not in css and 'line-height: 1.25' not in css
        # Both sit in the same grid cell, so each is as wide as the longer label; the
        # hidden one keeps its space but is invisible.
        assert '\n.run-slot { display: inline-grid; }' in css
        assert '\n.run-slot > button { grid-area: 1 / 1; }' in css
        assert '\n.run-slot > button[hidden] { display: block; visibility: hidden; }' in css
        slot = re.search(r'<span class="run-slot">\s*(.*?)\s*</span>', html, re.S)
        assert slot, 'run-slot wrapper missing'
        buttons = re.findall(r'<button[^>]*>', slot.group(1))
        assert buttons == ['<button type="button" id="startBtn">',
                           '<button type="button" id="stopBtn" hidden>']


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
