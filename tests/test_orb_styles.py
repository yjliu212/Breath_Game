"""Optional breathing-orb styles: the circle cycles plain → taiji → mist → aura → particles → lotus."""
import re

import pytest

import i18n
from conftest import register

EN = {'Accept-Language': 'en-US,en;q=0.9'}
LABELS = {'zh': '切换呼吸球样式', 'en': 'Change breathing orb style'}
STYLES = ['plain', 'taiji', 'mist', 'aura', 'particles', 'lotus']


@pytest.fixture(params=['guest', 'user'])
def home_html(request, client):
    if request.param == 'user':
        register(client)
    return {lang: client.get('/', headers=h).get_data(as_text=True)
            for lang, h in (('zh', {}), ('en', EN))}


@pytest.fixture
def orb_js(client):
    resp = client.get('/static/orb.js')
    assert resp.status_code == 200
    assert 'javascript' in resp.mimetype
    return resp.get_data(as_text=True)


def circle_tag(html):
    m = re.search(r'<div class="circle" id="circle"[^>]*>', html)
    assert m, 'circle missing'
    return m.group(0)


def page_css(html):
    start = html.index('<style>\nbody {')
    return html[start:html.index('</style>', start)]


def test_i18n_key_has_both_languages():
    for lang, label in LABELS.items():
        assert i18n.t('home.orb_switch', lang) == label


@pytest.mark.parametrize('lang', ['zh', 'en'])
def test_circle_is_an_accessible_button(home_html, lang):
    tag = circle_tag(home_html[lang])
    label = LABELS[lang]
    assert 'role="button"' in tag and 'tabindex="0"' in tag
    assert f'aria-label="{label}"' in tag and f'title="{label}"' in tag
    other = LABELS['en' if lang == 'zh' else 'zh']
    assert other not in home_html[lang]


def test_default_markup_is_the_plain_circle(home_html):
    for html in home_html.values():
        # Empty element, same class, no style-specific class or layer in the markup.
        assert re.search(r'<div class="circle" id="circle"[^>]*></div>', html)
        assert 'orb-layer' not in circle_tag(html) and 'data-orb' not in circle_tag(html)
        css = page_css(html)
        m = re.search(r'\n\.circle \{([^}]*)\}', css)
        assert m, 'base circle rule missing'
        for decl in ('width: 160px;', 'height: 160px;', 'margin: 30px auto;', 'border-radius: 50%;',
                     'background: radial-gradient(circle, #22c55e, #14532d);', 'will-change: transform;'):
            assert decl in m.group(1), decl
        # Only other styles drop the green fill; layers are absolutely positioned (no layout shift).
        assert '.circle.orb-alt { background: none; }' in css
        assert re.search(r'\.orb-layer \{[^}]*position: absolute;[^}]*pointer-events: none;', css)
        assert re.search(r'\.circle \{ position: relative; z-index: 0; cursor: pointer;', css)


def test_orb_layer_never_blocks_clicks_or_covers_controls(home_html):
    css = page_css(home_html['zh'])
    layer = re.search(r'\n\.orb-layer \{([^}]*)\}', css)
    assert layer, '.orb-layer rule missing'
    rule = layer.group(1)
    assert 'pointer-events: none;' in rule
    assert 'background: transparent;' in rule
    # Clipped to the circle's 80px radius + ~6px (~8px at the 1.3 scale): no box, no overflow.
    assert 'clip-path: circle(86px at 50% 50%);' in rule
    assert '.orb-layer, .orb-layer * { pointer-events: none; }' in css
    assert '.orb-layer svg { overflow: hidden; background: transparent; }' in css
    # The buttons and the phase text stack above the circle and its layers.
    assert re.search(r'\n\.circle \{ position: relative; z-index: 0;', css)
    assert '#settingsForm button, #guideText { position: relative; z-index: 1; }' in css
    # The mist glow fades out by 86px rather than filling its 240px box.
    assert 'rgba(34,197,94,0) 86px' in css


def test_orb_styles_stay_within_the_circle_footprint(orb_js):
    assert 'var R = 80, EDGE = 86;' in orb_js
    # No oversized halos or visible overflow from the old 240px drawings.
    for big in ('r="118"', 'r="96"', 'R * 1.45', 'overflow: visible', '80 * BIG + 30'):
        assert big not in orb_js, big
    # Every SVG filter uses the fixed user-space region instead of a bbox-relative box.
    filters = re.findall(r'<filter id="[^"]+"([^>]*)>', orb_js)
    assert filters and all(f == "' + FREGION + '" for f in filters), filters
    assert 'filterUnits="userSpaceOnUse"' in orb_js
    # Lotus petals open to at most 56 + 25 = 81 units; particles fade out before EDGE.
    assert 'this.place(this.OUTER, 0, tw, 56 + 25 * o,' in orb_js
    assert 'var edge = smooth((EDGE - rr - d * 0.18) / 10);' in orb_js
    # Taiji trigram ring ends inside the circle.
    assert 'var y = -(58 + i * 5);' in orb_js


def test_engine_scale_unchanged_and_feeds_the_orb(home_html):
    html = home_html['zh']
    script = html[html.index('<script>\n(function'):]
    assert 'const IDLE = 1, SMALL = 0.6, BIG = 1.3;' in script
    assert 'function setScale(s) { circle.style.transform = "scale(" + s + ")"; }' in script
    assert 'orb.breath(s.key, p, scale);' in script
    assert 'orb.breath("idle", 0, IDLE);' in script
    # Works without orb.js too.
    assert 'const orb = window.BreathOrb || { breath: function () {} };' in script
    for key in ('inhale', 'hold1', 'exhale', 'hold2'):
        assert f'{{ key: "{key}",' in script


def test_orb_script_is_served_from_our_origin(home_html, orb_js):
    for html in home_html.values():
        assert '<script src="/static/orb.js"></script>' in html
        # Loaded before the engine, which reads window.BreathOrb.
        assert html.index('src="/static/orb.js"') < html.index('<script>\n(function')
    assert orb_js.strip()


def test_style_order_and_storage_key(orb_js):
    m = re.search(r'var STYLES = \[([^\]]*)\];', orb_js)
    assert m
    assert re.findall(r'"(\w+)"', m.group(1)) == STYLES
    assert 'var KEY = "breath.orb";' in orb_js
    assert 'localStorage.getItem(KEY)' in orb_js and 'localStorage.setItem(KEY, name)' in orb_js
    # Unknown values fall back to plain; storage errors are caught.
    assert 'return i < 0 ? 0 : i;' in orb_js
    assert orb_js.count('try {') >= 2


def test_orb_input_and_test_hook(orb_js):
    assert 'circle.addEventListener("click"' in orb_js
    assert 'circle.addEventListener("keydown"' in orb_js
    assert 'e.key === "Enter"' in orb_js and 'e.key === " "' in orb_js
    assert 'e.preventDefault();' in orb_js
    assert 'window.__orb = {' in orb_js
    for fn in ('set:', 'next:', 'current:'):
        assert fn in orb_js
    # Never touches practice or the form.
    for forbidden in ('startBtn', 'stopBtn', 'saveBtn', 'submit', 'settingsForm', '.click()'):
        assert forbidden not in orb_js


def test_orb_code_is_self_contained(home_html, orb_js):
    assert 'http' not in orb_js.lower()
    assert '//cdn' not in orb_js and 'import ' not in orb_js
    for html in home_html.values():
        assert not re.search(r'<script[^>]+src="(https?:)?//', html)
        assert ' onclick=' not in html and ' onkeydown=' not in html


def test_performance_guards(orb_js):
    assert 'document.hidden' in orb_js and 'visibilitychange' in orb_js
    assert 'cancelAnimationFrame' in orb_js
    assert 'Math.min(2, window.devicePixelRatio || 1)' in orb_js
    assert 'var N = this.N = 96;' in orb_js                 # lighter mist canvas
    assert 'prefers-reduced-motion: reduce' in orb_js


def test_no_extra_visible_text(home_html):
    for lang, html in home_html.items():
        body = html[html.index('<body>'):html.index('<script src=')]
        visible = re.sub(r'<[^>]+>', ' ', body)
        # The orb label exists only as attributes, never as visible text.
        assert LABELS[lang] not in visible
        for word in ('Taiji', 'Mist', 'Aura', 'Particles', 'Lotus', '太极', '云雾', '光晕', '粒子', '莲花'):
            assert word not in html
        assert html.count(LABELS[lang]) == 2          # aria-label + title only
