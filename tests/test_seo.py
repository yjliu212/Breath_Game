"""SEO / share-preview metadata: Open Graph, Twitter cards, canonical, robots.txt, sitemap.xml."""
import os
import struct
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest

import i18n
from conftest import ROOT, make_app

SITE = 'https://www.breathgame.net'
EN = {'Accept-Language': 'en-US,en;q=0.9'}
ZH = {'Accept-Language': 'zh-CN,zh;q=0.9'}
SITEMAP_NS = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


class HeadParser(HTMLParser):
    """Collect <meta> and <link> tags from the document."""

    def __init__(self):
        super().__init__()
        self.meta = {}        # property/name -> list of content values
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = a.get('property') or a.get('name')
            if key:
                self.meta.setdefault(key, []).append(a.get('content'))
        elif tag == 'link':
            self.links.append(a)


def parse_head(html):
    p = HeadParser()
    p.feed(html)
    return p


def one(head, key):
    values = head.meta.get(key, [])
    assert len(values) == 1, (key, values)
    return values[0]


def canonical(head):
    hrefs = [link['href'] for link in head.links if link.get('rel') == 'canonical']
    assert len(hrefs) == 1, hrefs
    return hrefs[0]


# ---------------------------------------------------------------- meta tags
LANG_CASES = [
    ('zh', ZH, 'zh_CN', 'en_US', 'og-image-zh.png'),
    ('en', EN, 'en_US', 'zh_CN', 'og-image-en.png'),
]


@pytest.mark.parametrize('lang, headers, locale, alt_locale, image', LANG_CASES)
def test_home_share_meta(client, lang, headers, locale, alt_locale, image):
    head = parse_head(client.get('/', headers=headers).get_data(as_text=True))
    title = i18n.t('site.name', lang)
    desc = i18n.t('meta.og_description', lang)
    image_url = f'{SITE}/static/{image}'

    assert canonical(head) == SITE + '/'
    assert one(head, 'og:url') == SITE + '/'
    assert one(head, 'og:type') == 'website'
    assert one(head, 'og:title') == title
    assert one(head, 'og:site_name') == title
    assert one(head, 'og:description') == desc
    assert one(head, 'og:locale') == locale
    assert head.meta['og:locale:alternate'] == [alt_locale]
    assert one(head, 'og:image') == image_url
    assert one(head, 'og:image:width') == '1200'
    assert one(head, 'og:image:height') == '630'
    assert one(head, 'og:image:alt') == i18n.t('meta.og_image_alt', lang)
    assert one(head, 'twitter:card') == 'summary_large_image'
    assert one(head, 'twitter:title') == title
    assert one(head, 'twitter:description') == desc
    assert one(head, 'twitter:image') == image_url
    assert one(head, 'description') == i18n.t('meta.description', lang)
    assert 'robots' not in head.meta          # home page is indexable


def test_cookie_language_selects_image(client):
    client.get('/lang/en')
    head = parse_head(client.get('/', headers=ZH).get_data(as_text=True))
    assert one(head, 'og:image').endswith('/og-image-en.png')
    assert one(head, 'og:locale') == 'en_US'


@pytest.mark.parametrize('lang, headers', [('zh', ZH), ('en', EN)])
def test_seo_strings_translated(lang, headers):
    other = 'en' if lang == 'zh' else 'zh'
    for key in ('meta.og_image_alt', 'meta.og_description', 'site.name'):
        assert i18n.t(key, lang) and i18n.t(key, lang) != i18n.t(key, other)


def test_canonical_ignores_query_string_and_host_header(client):
    resp = client.get('/?utm_source=x&lang=en', headers={'Host': 'evil.example', **EN})
    html = resp.get_data(as_text=True)
    head = parse_head(html)
    assert canonical(head) == SITE + '/'
    assert one(head, 'og:url') == SITE + '/'
    assert one(head, 'og:image').startswith(SITE + '/static/')
    assert 'evil.example' not in html
    # (The language switch in <body> keeps the query in its next= link; that's intended.)
    assert 'utm_source' not in html.split('</head>')[0]


@pytest.mark.parametrize('path', ['/login', '/register'])
def test_auth_pages_canonical_and_noindex(client, path):
    head = parse_head(client.get(path, headers=EN).get_data(as_text=True))
    assert canonical(head) == SITE + path
    assert one(head, 'og:url') == SITE + path
    assert one(head, 'robots') == 'noindex, follow'
    assert one(head, 'twitter:card') == 'summary_large_image'


def test_site_url_is_configurable(tmp_path):
    app = make_app(tmp_path / 'site.db', SITE_URL='https://staging.example.org/')
    client = app.test_client()
    head = parse_head(client.get('/', headers=EN).get_data(as_text=True))
    assert canonical(head) == 'https://staging.example.org/'
    assert one(head, 'og:image') == 'https://staging.example.org/static/og-image-en.png'
    xml = client.get('/sitemap.xml').get_data(as_text=True)
    assert '<loc>https://staging.example.org/</loc>' in xml


def test_default_site_url(app):
    assert app.config['SITE_URL'] == SITE


# ---------------------------------------------------------------- og images
@pytest.mark.parametrize('name', ['og-image-en.png', 'og-image-zh.png'])
def test_og_image_files(client, name):
    path = os.path.join(ROOT, 'static', name)
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    width, height = struct.unpack('>II', data[16:24])     # IHDR
    assert (width, height) == (1200, 630)
    assert len(data) < 300 * 1024
    resp = client.get(f'/static/{name}')
    assert resp.status_code == 200 and resp.mimetype == 'image/png'
    resp.close()


# ---------------------------------------------------------------- sitemap.xml
def test_sitemap(client):
    resp = client.get('/sitemap.xml')
    assert resp.status_code == 200
    assert resp.mimetype == 'application/xml'
    root = ET.fromstring(resp.data)
    assert root.tag == SITEMAP_NS + 'urlset'
    locs = [el.text for el in root.iter(SITEMAP_NS + 'loc')]
    assert locs == [SITE + '/']
    body = resp.get_data(as_text=True)
    for private in ('/login', '/register', '/logout', '/api/', '/save_settings', '/lang/'):
        assert private not in body
    assert 'hreflang' not in body     # language is cookie-based, same URL


def test_sitemap_same_for_any_language(client):
    assert client.get('/sitemap.xml', headers=EN).data == client.get('/sitemap.xml', headers=ZH).data


# ---------------------------------------------------------------- robots.txt
def test_robots_txt(client):
    resp = client.get('/robots.txt')
    assert resp.status_code == 200
    assert resp.mimetype == 'text/plain'
    lines = [ln.strip() for ln in resp.get_data(as_text=True).splitlines() if ln.strip()]
    resp.close()
    assert lines[0] == 'User-agent: *'
    assert 'Allow: /' in lines
    for path in ('/api/', '/logout', '/save_settings', '/lang/'):
        assert f'Disallow: {path}' in lines
    # Login/register carry a noindex meta tag, so crawlers must be allowed to fetch them.
    assert not any(ln.startswith('Disallow: /login') or ln.startswith('Disallow: /register')
                   for ln in lines)
    assert 'Disallow: /' not in lines
    assert f'Sitemap: {SITE}/sitemap.xml' in lines


def test_google_site_verification_file(client):
    resp = client.get('/googlec6cb5e372d7fcf40.html')
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).strip() == 'google-site-verification: googlec6cb5e372d7fcf40.html'
