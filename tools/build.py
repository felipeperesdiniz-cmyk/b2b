#!/usr/bin/env python3
"""Builds the bilingual site. Run from anywhere: python3 tools/build.py

Hand-edited sources (Portuguese): index.html, garanhoes/*.html
Content for generated pages: tools/content_*.py
Everything under en/, matrizes/, atletas/, noticias/, guias/ and the hub pages is generated.

The English home and stallion pages are made from the Portuguese files plus the dictionary in
tools/content_i18n.py. If a Portuguese text changes and has no translation, the build stops and
lists it, so the two languages cannot drift apart silently.
"""
import datetime, html, json, os, posixpath, re, struct, subprocess, sys, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content_i18n import T, KEEP, COAT, CAT, UI
from content_horses import EXTRA_HORSES, HORSE_NOTES
from content_news import NEWS, OLD_URLS
from content_guides import GUIDES, FAQ, ABOUT, BREEDING, AUCTIONS, GLOSSARY

BASE = 'https://b2branch.com.br'
TODAY = datetime.date.today().isoformat()
PHONE = '+55 (24) 99944-2266'
PHONE_E164 = '+5524999442266'
EMAIL = 'contato@b2branch.com.br'
SOCIAL = ['https://www.instagram.com/b2branch/', 'https://www.facebook.com/people/B2B-Ranch/100050369475180/',
          'https://www.youtube.com/@B2BRanch', 'https://www.tiktok.com/@b2branch']
LANGS = ('pt', 'en')
HTML_LANG = {'pt': 'pt-BR', 'en': 'en'}
OG_LOCALE = {'pt': 'pt_BR', 'en': 'en_US'}
MONTHS = {'pt': 'jan fev mar abr mai jun jul ago set out nov dez'.split(),
          'en': 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()}
DEFAULT_OG = 'assets/og/home.jpg'

SECTIONS = {  # section -> (pt folder, en folder)
    'stallions': ('garanhoes', 'en/stallions'), 'mares': ('matrizes', 'en/broodmares'),
    'athletes': ('atletas', 'en/athletes'), 'news': ('noticias', 'en/news'), 'guides': ('guias', 'en/guides')}
HUBS = {  # key -> (pt path, en path)
    'home': ('index.html', 'en/index.html'), 'stallions': ('garanhoes.html', 'en/stallions.html'),
    'mares': ('matrizes.html', 'en/broodmares.html'), 'athletes': ('atletas.html', 'en/athletes.html'),
    'news': ('noticias.html', 'en/news.html'), 'guides': ('guias.html', 'en/guides.html'),
    'about': ('sobre.html', 'en/about.html'), 'contact': ('contato.html', 'en/contact.html'),
    'films': ('filmes.html', 'en/films.html'), 'faq': ('perguntas-frequentes.html', 'en/faq.html'),
    'breeding': ('genetica-e-coberturas.html', 'en/genetics-and-breeding.html'),
    'auctions': ('leiloes.html', 'en/auctions.html'), 'glossary': ('glossario.html', 'en/glossary.html')}
NAV = ['about', 'stallions', 'mares', 'athletes', 'news', 'guides', 'contact']
E = html.escape

ROUTES = {}      # pt path -> en path
PAGES = []       # {'pt': path, 'en': path} for the sitemap
HORSES = {}      # name -> horse dict
written = {}


def L(lang, key):
    return UI[key][0 if lang == 'pt' else 1]


def t2(pair, lang):
    return pair[0] if lang == 'pt' else pair[1]


def url(path):
    if path == 'index.html':
        return BASE + '/'
    if path.endswith('/index.html'):
        return BASE + '/' + path[:-len('index.html')]
    return BASE + '/' + path


def rel(frm, to):
    return posixpath.relpath(to, posixpath.dirname(frm) or '.')


def fmt_date(iso, lang):
    y, m, d = iso.split('-')
    mon = MONTHS[lang][int(m) - 1]
    return f'{int(d)} {mon} {y}' if lang == 'pt' else f'{mon} {int(d)}, {y}'


def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def webp_size(path):
    with open(os.path.join(ROOT, path), 'rb') as f:
        d = f.read(40)
    kind = d[12:16]
    if kind == b'VP8 ':
        return struct.unpack('<H', d[26:28])[0] & 0x3fff, struct.unpack('<H', d[28:30])[0] & 0x3fff
    if kind == b'VP8L':
        b = struct.unpack('<I', d[21:25])[0]
        return (b & 0x3fff) + 1, ((b >> 14) & 0x3fff) + 1
    return int.from_bytes(d[24:27], 'little') + 1, int.from_bytes(d[27:30], 'little') + 1


def og_for(img):
    """A JPEG share image for a webp photo (WhatsApp and some crawlers ignore webp)."""
    if not img:
        return DEFAULT_OG
    out = 'assets/og/p-' + re.sub(r'[^a-z0-9]+', '-', img[len('assets/'):-len('.webp')].lower()) + '.jpg'
    full = os.path.join(ROOT, out)
    if not os.path.exists(full):
        r = subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '78', '--resampleWidth', '1200',
                            os.path.join(ROOT, img), '--out', full], capture_output=True)
        if r.returncode or not os.path.exists(full):
            return DEFAULT_OG
    return out


# ---------- structured data ----------
def org_ld():
    return {'@type': ['Organization', 'LocalBusiness'], '@id': BASE + '/#org', 'name': 'B2B Ranch', 'url': BASE + '/',
            'logo': BASE + '/assets/logo.webp', 'image': BASE + '/' + DEFAULT_OG,
            'slogan': 'Apaixonados por grandes cavalos', 'telephone': PHONE_E164, 'email': EMAIL,
            'description': 'Haras de criação e treinamento de cavalos Quarto de Milha de alta performance para os Três Tambores, em Três Rios, Rio de Janeiro, Brasil.',
            'address': {'@type': 'PostalAddress', 'addressLocality': 'Três Rios', 'addressRegion': 'RJ', 'addressCountry': 'BR'},
            'areaServed': 'BR', 'founder': [{'@type': 'Person', 'name': 'Odilon Diniz'}, {'@type': 'Person', 'name': 'Maria Izabel (Bebel) Diniz'}],
            'knowsAbout': ['Cavalo Quarto de Milha', 'American Quarter Horse', 'Três Tambores', 'barrel racing', 'Seis Balizas', 'pole bending'],
            'sameAs': SOCIAL}


def crumbs_ld(items):
    return {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': url(p)} for i, (n, p) in enumerate(items)]}


def ld_script(nodes):
    data = {'@context': 'https://schema.org', '@graph': nodes}
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/') + '</script>'


def alternates(path, lang):
    pt = path if lang == 'pt' else next(k for k, v in ROUTES.items() if v == path)
    en = ROUTES[pt]
    return pt, en


def alt_links(path, lang):
    pt, en = alternates(path, lang)
    return (f'<link rel="canonical" href="{url(path)}">\n'
            f'<link rel="alternate" hreflang="pt-BR" href="{url(pt)}">\n'
            f'<link rel="alternate" hreflang="en" href="{url(en)}">\n'
            f'<link rel="alternate" hreflang="x-default" href="{url(pt)}">')


def lang_button(path, lang):
    pt, en = alternates(path, lang)
    a = lambda code, target, label: (f'<a href="{rel(path, target)}" hreflang="{HTML_LANG[code]}" lang="{HTML_LANG[code]}"'
                                     + (' aria-current="true"' if code == lang else '') + f' title="{label}">{code.upper()}</a>')
    return ('<div class="lang" role="group" aria-label="' + L(lang, 'lang_label') + '">'
            + a('pt', pt, 'Ver em português') + a('en', en, 'View in English') + '</div>')


LANG_JS = ("<script>document.querySelectorAll('.lang a').forEach(a=>a.addEventListener('click',()=>{"
           "if(location.hash)a.hash=location.hash}))</script>")


def top(path, lang):
    home = HUBS['home'][LANGS.index(lang)]
    items = ''.join(f'<li><a href="{rel(path, HUBS[k][LANGS.index(lang)])}"'
                    + (' aria-current="page"' if HUBS[k][LANGS.index(lang)] == path else '')
                    + f'>{L(lang, "nav_" + k)}</a></li>' for k in NAV)
    return (f'<a class="brand" id="brand" href="{rel(path, home)}" aria-label="{L(lang, "home_label")}"><img src="{rel(path, "assets/logo-mark.webp")}" alt="B2B Ranch Quarter Horse" width="372" height="240"></a>\n'
            f'<header class="s-top"><nav aria-label="{L(lang, "nav_label")}"><ul class="s-links">{items}</ul>'
            f'<details class="s-menu"><summary>Menu</summary><ul>{items}</ul></details>{lang_button(path, lang)}</nav></header>')


def sitemap_links(path, lang):
    i = LANGS.index(lang)
    col = lambda title, links: (f'<div><h2>{title}</h2><ul>' + ''.join(f'<li><a href="{rel(path, p)}">{E(n)}</a></li>' for n, p in links) + '</ul></div>')
    hub = lambda k: (L(lang, 'nav_' + k), HUBS[k][i])
    stallions = [(n, f'{SECTIONS["stallions"][i]}/{s}.html') for n, s in (('Tux N Rolls', 'tux-n-rolls'), ('B2B Lucius Ta Fame', 'lucius-ta-fame'), ('Adios Pantalones', 'adios-pantalones'))]
    guides = [(t2(g['nav'], lang), f'{SECTIONS["guides"][i]}/{t2(g["slug"], lang)}.html') for g in GUIDES]
    return ('<div class="s-map">'
            + col(L(lang, 'foot_ranch'), [hub(k) for k in ('home', 'about', 'breeding', 'auctions', 'films', 'news', 'contact')])
            + col(L(lang, 'nav_stallions'), stallions + [hub('mares'), hub('athletes')])
            + col(L(lang, 'nav_guides'), guides + [hub('glossary'), hub('faq')])
            + '</div>')


def foot(path, lang):
    home = HUBS['home'][LANGS.index(lang)]
    return (f'<footer class="s-foot pad"><div class="wrap">{sitemap_links(path, lang)}'
            f'<p class="s-nap"><b>B2B Ranch</b> · {L(lang, "nap")} · <a href="tel:{PHONE_E164}">{PHONE}</a> · <a href="mailto:{EMAIL}">{EMAIL}</a></p>'
            f'<p class="s-copy"><span>© {TODAY[:4]} B2B Ranch · {L(lang, "slogan")}</span><a href="{rel(path, home)}">b2branch.com.br</a></p></div></footer>')


def wa_link(msg):
    return 'https://wa.me/5524999442266?text=' + urllib.parse.quote(msg)


def cta(lang, heading, msg, text=None):
    return (f'<section class="g-cta pad" aria-label="{L(lang, "contact")}"><div class="wrap"><h2>{E(heading)}</h2><div>'
            f'<p>{E(text or L(lang, "cta_text"))}</p><span class="phone">{PHONE}</span>'
            f'<a class="btn" href="{E(wa_link(msg))}" target="_blank" rel="noopener">{L(lang, "cta_btn")} <span aria-hidden="true">→</span></a></div></div></section>')


def crumbs_html(path, items):
    out = ''.join((f'<li><a href="{rel(path, p)}">{E(n)}</a></li>' if p != path else f'<li aria-current="page">{E(n)}</li>') for n, p in items)
    return f'<nav class="s-crumbs wrap pad" aria-label="Breadcrumb"><ol>{out}</ol></nav>'


def page(path, lang, title, desc, body, img=None, kind='website', nodes=(), css=('garanhao', 'noticia', 'pagina'), published=None, img_alt=''):
    if len(desc) > 165:
        problems.append(f'{path}: description is {len(desc)} chars')
    og = og_for(img)
    d = '../' * path.count('/')
    head = [
        '<!doctype html>', f'<html lang="{HTML_LANG[lang]}">', '<head>', '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        f'<title>{E(title)}</title>', f'<meta name="description" content="{E(desc)}">', '<meta name="theme-color" content="#f4f2ee">',
        alt_links(path, lang), f'<meta property="og:type" content="{kind}">', f'<meta property="og:locale" content="{OG_LOCALE[lang]}">',
        f'<meta property="og:locale:alternate" content="{OG_LOCALE["en" if lang == "pt" else "pt"]}">',
        '<meta property="og:site_name" content="B2B Ranch">', f'<meta property="og:url" content="{url(path)}">',
        f'<meta property="og:title" content="{E(title)}">', f'<meta property="og:description" content="{E(desc)}">',
        f'<meta property="og:image" content="{BASE}/{og}">']
    if img_alt:
        head.append(f'<meta property="og:image:alt" content="{E(img_alt)}">')
    if published:
        head.append(f'<meta property="article:published_time" content="{published}">')
    head += ['<meta name="twitter:card" content="summary_large_image">', f'<link rel="icon" href="{d}assets/logo.webp">',
             '<link rel="preconnect" href="https://fonts.googleapis.com">', '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400..600&display=swap">']
    head += [f'<link rel="stylesheet" href="{d}assets/{c}.css">' for c in css]
    head += [ld_script([org_ld()] + list(nodes)), '</head>', '<body>', top(path, lang), body, foot(path, lang),
             "<script>addEventListener('scroll',()=>document.getElementById('brand').classList.toggle('small',scrollY>40),{passive:true})</script>",
             LANG_JS, '</body>', '</html>', '']
    write(path, '\n'.join(head))


def write(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as f:
        f.write(text)
    written[path] = text


def register(pt, en):
    ROUTES[pt] = en
    PAGES.append({'pt': pt, 'en': en})


# ---------- horses ----------
def parse_home_horses():
    src = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    mz = src[src.index('<section id="matrizes"'):src.index('<section id="atletas"')]
    at = src[src.index('<section id="atletas"'):src.index('<section id="noticias"')]
    seen = {}
    for sec, chunk in (('mares', mz), ('athletes', at)):
        for li in re.findall(r'<li(?: data-mz="[^"]*")?>(<b>.*?)</li>', chunk, re.S):
            m = re.match(r'<b>(?:<a [^>]*>)?([^<]+)(?:</a>)?(<em>[^<]*</em>)?</b><span>([^<]+)</span>', li)
            name = html.unescape(m.group(1))
            if name in seen:
                seen[name]['also_athlete'] = True
                continue
            sire, dam = [x.strip() for x in html.unescape(m.group(3)).split('×')]
            im = re.search(r'<img src="(assets/[^"]+)" alt="([^"]*)"', li)
            text = re.search(r'<p>(.*?)</p>', li, re.S).group(1)
            seen[name] = {'name': name, 'section': sec, 'sire': sire, 'dam': dam, 'slug': slugify(name), 'text': html.unescape(text),
                          'also_athlete': bool(m.group(2)), 'img': im.group(1) if im else None, 'alt': html.unescape(im.group(2)) if im else '',
                          'gen': None}
    # which Potro do Futuro generation each athlete belongs to, as grouped on the home page
    for year, block in re.findall(r'<h3 class="mz-sub">Potros do Futuro (\d{4})</h3>\s*<ul class="mz-list pf">(.*?)</ul>', at, re.S):
        for nm in re.findall(r'<b>(?:<a [^>]*>)?([^<]+)', block):
            seen[html.unescape(nm)]['gen'] = year
    for h in EXTRA_HORSES:
        seen[h['name']] = dict({'section': 'athletes', 'slug': slugify(h['name']), 'also_athlete': False, 'img': None, 'alt': '', 'gen': None}, **h)
    return seen


def horse_path(h, lang):
    return f'{SECTIONS[h["section"]][LANGS.index(lang)]}/{h["slug"]}.html'


STALLION_FILES = {'Tux N Rolls': 'tux-n-rolls', 'B2B Lucius Ta Fame': 'lucius-ta-fame', 'Adios Pantalones': 'adios-pantalones'}


def name_path(name, lang):
    if name in STALLION_FILES:
        return f'{SECTIONS["stallions"][LANGS.index(lang)]}/{STALLION_FILES[name]}.html'
    return horse_path(HORSES[name], lang) if name in HORSES else None


def link_names(text, path, lang, skip=()):
    """Links the first mention of each horse with a page. text is already-safe HTML with no tags inside names."""
    names = sorted([n for n in list(HORSES) + list(STALLION_FILES) if n not in skip], key=len, reverse=True)
    seen = set()
    def sub(m):
        n = m.group(0)
        if n in seen:
            return n
        seen.add(n)
        return f'<a href="{rel(path, name_path(n, lang))}">{n}</a>'
    return re.sub('|'.join(re.escape(n) for n in names), sub, text)


def tr(text, ctx=''):
    if text in T:
        return T[text]
    missing.setdefault(text, ctx)
    return text


def result_rows():
    """Every published result, from the news data, keyed by horse."""
    out = {}
    for n in NEWS:
        for b in n['body']:
            if b[0] == 'r':
                for row in b[1]:
                    out.setdefault(row[0], []).append((n, row))
    return out


def place_label(p, lang):
    if p is None:
        return ''
    if lang == 'pt':
        return f'{p}º'
    return f'{p}{ {1: "st", 2: "nd", 3: "rd"}.get(p, "th") }'


def cat_label(c, lang):
    if lang == 'pt':
        return c
    if c not in CAT:
        missing.setdefault(c, 'category')
    return CAT.get(c, c)


def build_horse(h, results):
    name = h['name']
    sibs = [o for o in HORSES.values() if o is not h and o['sire'] == h['sire'] and o['dam'] == h['dam']]
    kids = [o for o in HORSES.values() if name in (o['sire'], o['dam'])]
    related = []
    seen = set()
    for n, _ in results.get(name, []):
        if n['slug'][0] not in seen:
            seen.add(n['slug'][0])
            related.append(n)
    for n in NEWS:
        if n['slug'][0] not in seen and any(name in b[1] for b in n['body'] if b[0] in ('p', 'h')):
            seen.add(n['slug'][0])
            related.append(n)
    siblings_in_section = [o for o in HORSES.values() if o['section'] == h['section']]
    i = siblings_in_section.index(h)
    nxt = siblings_in_section[(i + 1) % len(siblings_in_section)]
    note = HORSE_NOTES.get(name)
    coat = None
    m = re.search(r'alaz|tordilh|castanh|palomino', h.get('alt', ''))
    if m:
        coat = {'alaz': 'alazã', 'tordilh': 'tordilha', 'castanh': 'castanha', 'palomino': 'palomino'}[m.group(0)]
    for lang in LANGS:
        path = horse_path(h, lang)
        idx = LANGS.index(lang)
        pedigree = f'{h["sire"]} × {h["dam"]}'
        if h['section'] == 'mares':
            role = L(lang, 'role_mare') + (' · ' + L(lang, 'role_also') if h['also_athlete'] else '')
            lead = (f'{name} integra o plantel de matrizes do B2B Ranch, haras de cavalos Quarto de Milha em Três Rios (RJ) dedicado aos Três Tambores. Pai: {h["sire"]}. Mãe: {h["dam"]}.'
                    if lang == 'pt' else
                    f'{name} is a broodmare at B2B Ranch, a Quarter Horse breeding and training ranch in Três Rios, Rio de Janeiro, Brazil, focused on barrel racing. Sire: {h["sire"]}. Dam: {h["dam"]}.')
        else:
            role = L(lang, 'role_athlete') + (f' · Potro do Futuro {h["gen"]}' if h['gen'] else '')
            lead = (f'{name} é atleta da criação B2B Ranch, haras de cavalos Quarto de Milha em Três Rios (RJ) dedicado aos Três Tambores. Pai: {h["sire"]}. Mãe: {h["dam"]}.'
                    if lang == 'pt' else
                    f'{name} is an athlete bred by B2B Ranch, a Quarter Horse breeding and training ranch in Três Rios, Rio de Janeiro, Brazil, focused on barrel racing. Sire: {h["sire"]}. Dam: {h["dam"]}.')
        text = h['text'] if lang == 'pt' else h.get('text_en') or tr(h['text'], name)
        alt = h['alt'] if lang == 'pt' else tr(h['alt'], name) if h['alt'] else ''
        hub = HUBS[h['section']][idx]
        crumb = [(L(lang, 'nav_home'), HUBS['home'][idx]), (L(lang, 'nav_' + h['section']), hub), (name, path)]
        fig = ''
        if h['img']:
            w, hh = webp_size(h['img'])
            fig = f'<figure class="p-photo wrap pad"><img src="{rel(path, h["img"])}" alt="{E(alt)}" width="{w}" height="{hh}" fetchpriority="high"></figure>'
        sheet = [(L(lang, 'sire'), h['sire']), (L(lang, 'dam'), h['dam'])]
        if coat:
            sheet.append((L(lang, 'coat'), coat if lang == 'pt' else COAT[coat]))
        sheet.append((L(lang, 'breed'), L(lang, 'breed_v')))
        sheet.append((L(lang, 'discipline'), L(lang, 'discipline_v')))
        sheet.append((L(lang, 'ranch'), 'B2B Ranch'))
        sheet_html = '<dl class="g-sheet">' + ''.join(
            f'<div><dt>{k}</dt><dd>' + (f'<a href="{rel(path, name_path(v, lang))}">{E(v)}</a>' if name_path(v, lang) else E(v)) + '</dd></div>' for k, v in sheet) + '</dl>'
        fam = []
        for rel_name, label in ((h['sire'], L(lang, 'sire')), (h['dam'], L(lang, 'dam'))):
            if name_path(rel_name, lang):
                fam.append((rel_name, label, ''))
        fam += [(o['name'], L(lang, 'full_sib'), f'{o["sire"]} × {o["dam"]}') for o in sibs]
        fam += [(o['name'], L(lang, 'offspring'), f'{o["sire"]} × {o["dam"]}') for o in kids]
        fam_html = ''
        if fam:
            fam_html = (f'<section class="g-family wrap pad"><h2>{L(lang, "family_h").format(name=E(name))}</h2><ul>' + ''.join(
                f'<li><b><a href="{rel(path, name_path(n, lang))}">{E(n)}</a></b><em>{lb}</em><span>{E(extra)}</span></li>' for n, lb, extra in fam) + '</ul></section>')
        res_html = ''
        if name in results:
            rows = ''.join(
                f'<tr><td>{place_label(r[1], lang)}</td><td>{E(cat_label(r[2], lang))}</td><td><a href="{rel(path, news_path(n, lang))}">{E(t2(n["event"], lang))}</a></td>'
                f'<td>{E(r[3] or "")}</td><td>{E(r[4] or "")}</td><td>{fmt_date(n["date"], lang)}</td></tr>' for n, r in results[name])
            res_html = (f'<section class="p-results wrap pad"><h2>{L(lang, "results_h").format(name=E(name))}</h2><div class="p-table"><table><thead><tr>'
                        + ''.join(f'<th scope="col">{L(lang, k)}</th>' for k in ('th_place', 'th_cat', 'th_event', 'th_rider', 'th_time', 'th_date'))
                        + f'</tr></thead><tbody>{rows}</tbody></table></div><p class="p-note">{L(lang, "results_note")}</p></section>')
        news_html = ''
        if related:
            news_html = (f'<section class="p-links wrap pad"><h2>{L(lang, "news_about").format(name=E(name))}</h2><ul>' + ''.join(
                f'<li><a href="{rel(path, news_path(n, lang))}">{E(t2(n["title"], lang))}</a> <time datetime="{n["date"]}">{fmt_date(n["date"], lang)}</time></li>' for n in related[:6]) + '</ul></section>')
        extra_p = f'<p>{link_names(E(t2(note, lang)), path, lang, skip=(name,))}</p>' if note else ''
        body = (f'<main>{crumbs_html(path, crumb)}<article><header class="p-head wrap pad"><span class="label">{role}</span><h1>{E(name)}</h1><p class="p-ped">{E(pedigree)}</p></header>{fig}'
                f'<section class="p-copy wrap pad"><span class="label">{L(lang, "about_horse")}</span><div><p class="p-lead">{link_names(E(text), path, lang, skip=(name,))}</p>{extra_p}<p>{link_names(E(lead), path, lang, skip=(name,))}</p></div></section>'
                f'<div class="wrap pad">{sheet_html}</div>{fam_html and "<div class=p-gap></div>" + fam_html}{res_html}{news_html}</article>'
                + cta(lang, L(lang, 'cta_about').format(name=name), L(lang, 'wa_about').format(name=name))
                + f'<nav class="p-next wrap pad" aria-label="{L(lang, "next_label")}"><a href="{rel(path, hub)}">← {L(lang, "all_" + h["section"])}</a><a href="{rel(path, horse_path(nxt, lang))}">{E(nxt["name"])} →</a></nav></main>')
        title = f'{name}: {L(lang, "title_mare" if h["section"] == "mares" else "title_athlete")} {pedigree} · B2B Ranch'
        if len(title) > 70:
            title = f'{name} ({L(lang, "title_mare" if h["section"] == "mares" else "title_athlete")}) · B2B Ranch'
        short = re.sub(r'\s+', ' ', text)
        desc = f'{name} ({pedigree}). {short}'
        if len(desc) > 160:
            desc = desc[:157].rsplit(' ', 1)[0] + '…'
        page(path, lang, title, desc, body, img=h['img'], kind='article', img_alt=alt,
             nodes=[crumbs_ld(crumb), {'@type': 'WebPage', '@id': url(path), 'url': url(path), 'name': title, 'inLanguage': HTML_LANG[lang], 'about': {'@type': 'Thing', 'name': name, 'description': f'American Quarter Horse. {pedigree}'}, 'publisher': {'@id': BASE + '/#org'}}])


# ---------- news ----------
def news_path(n, lang):
    return f'{SECTIONS["news"][LANGS.index(lang)]}/{t2(n["slug"], lang)}.html'


def news_card(n, lang, path):
    w, h = webp_size(n['img'])
    return (f'<a class="n-card" href="{rel(path, news_path(n, lang))}"><span class="ph"><img src="{rel(path, n["img"])}" alt="" width="{w}" height="{h}" loading="lazy" decoding="async"></span>'
            f'<time datetime="{n["date"]}">{fmt_date(n["date"], lang)}</time><b>{E(t2(n["title"], lang))}</b></a>')


def result_li(row, lang, path):
    horse, place, cat, rider, tm = row
    who = link_names(E(horse), path, lang)
    parts = [x for x in (place_label(place, lang), E(cat_label(cat, lang))) if x]
    tail = (f', {E(rider)}' if rider else '') + (f' · {E(tm)}' if tm else '')
    return f'<li>{" · ".join(parts)}: {who}{tail}</li>'


def build_news():
    latest = sorted(NEWS, key=lambda n: n['date'], reverse=True)
    for n in NEWS:
        for lang in LANGS:
            path = news_path(n, lang)
            idx = LANGS.index(lang)
            title, lede = t2(n['title'], lang), t2(n['lede'], lang)
            alt = t2(n['alt'], lang)
            out = []
            for b in n['body']:
                if b[0] == 'p':
                    out.append(f'<p>{link_names(E(t2(b[1:3], lang)), path, lang)}</p>')
                elif b[0] == 'h':
                    out.append(f'<h2>{E(t2(b[1:3], lang))}</h2>')
                elif b[0] == 'l':
                    out.append('<ul>' + ''.join(f'<li>{link_names(E(t2(x, lang)), path, lang)}</li>' for x in b[1]) + '</ul>')
                elif b[0] == 'r':
                    out.append('<ul>' + ''.join(result_li(r, lang, path) for r in b[1]) + '</ul>')
            more = [o for o in latest if o is not n][:3]
            crumb = [(L(lang, 'nav_home'), HUBS['home'][idx]), (L(lang, 'nav_news'), HUBS['news'][idx]), (title, path)]
            w, h = webp_size(n['img'])
            body = (f'<main>{crumbs_html(path, crumb)}<article><header class="n-head wrap pad" style="padding-top:clamp(24px,4vh,48px)"><time class="label" datetime="{n["date"]}">{fmt_date(n["date"], lang)}</time>'
                    f'<h1>{E(title)}</h1><p>{E(lede)}</p></header>'
                    f'<figure class="n-hero wrap pad"><img src="{rel(path, n["img"])}" alt="{E(alt)}" width="{w}" height="{h}" fetchpriority="high" style="--pos:50% 40%"></figure>'
                    f'<div class="n-body pad">{"".join(out)}<p class="n-sign">B2B Ranch · {L(lang, "slogan")}</p></div></article>'
                    f'<section class="n-more wrap pad" aria-label="{L(lang, "more_news")}"><h2 class="label">{L(lang, "more_news")}</h2><div class="n-grid">{"".join(news_card(o, lang, path) for o in more)}</div></section></main>')
            full = f'{title} · B2B Ranch'
            if len(full) > 70:
                full = title if len(title) <= 70 else title[:67].rsplit(' ', 1)[0] + '…'
            page(path, lang, full, lede[:157].rsplit(' ', 1)[0] + '…' if len(lede) > 160 else lede, body, img=n['img'], kind='article', img_alt=alt, published=n['date'],
                 nodes=[crumbs_ld(crumb), {'@type': 'NewsArticle', '@id': url(path) + '#article', 'mainEntityOfPage': url(path), 'headline': title[:110], 'description': lede, 'inLanguage': HTML_LANG[lang],
                                           'datePublished': n['date'], 'dateModified': n['date'], 'image': BASE + '/' + n['img'], 'author': {'@id': BASE + '/#org'}, 'publisher': {'@id': BASE + '/#org'}}])


# ---------- hubs and guides ----------
def rich(blocks, path, lang):
    """blocks: ('p', pt, en) ('h', pt, en) ('l', [(pt, en), ...]) ('dl', [((pt, en), (pt, en)), ...])"""
    out = []
    blocks = [tuple(x.replace('href="MATRIZES"', f'href="{rel(path, HUBS["mares"][LANGS.index(lang)])}"') if isinstance(x, str) else x for x in b) for b in blocks]
    for b in blocks:
        if b[0] == 'p':
            out.append(f'<p>{link_names(t2(b[1:3], lang), path, lang)}</p>')
        elif b[0] == 'h':
            out.append(f'<h2>{E(t2(b[1:3], lang))}</h2>')
        elif b[0] == 'l':
            out.append('<ul>' + ''.join(f'<li>{link_names(t2(x, lang), path, lang)}</li>' for x in b[1]) + '</ul>')
        elif b[0] == 'dl':
            out.append('<dl class="p-terms">' + ''.join(f'<div><dt>{E(t2(k, lang))}</dt><dd>{link_names(t2(v, lang), path, lang)}</dd></div>' for k, v in b[1]) + '</dl>')
    return ''.join(out)


def text_page(key, lang, data, nodes=(), after=''):
    idx = LANGS.index(lang)
    path = HUBS[key][idx]
    title, h1, lede = t2(data['title'], lang), t2(data['h1'], lang), t2(data['lede'], lang)
    crumb = [(L(lang, 'nav_home'), HUBS['home'][idx]), (L(lang, 'nav_' + key), path)]
    fig = ''
    if data.get('img'):
        w, h = webp_size(data['img'])
        fig = f'<figure class="n-hero wrap pad"><img src="{rel(path, data["img"])}" alt="{E(t2(data["alt"], lang))}" width="{w}" height="{h}" fetchpriority="high" style="--pos:50% 40%"></figure>'
    body = (f'<main>{crumbs_html(path, crumb)}<article><header class="n-head wrap pad" style="padding-top:clamp(24px,4vh,48px)"><span class="label">{L(lang, "nav_" + key)}</span><h1>{E(h1)}</h1><p>{E(lede)}</p></header>{fig}'
            f'<div class="n-body pad">{rich(data["body"], path, lang)}</div></article>{after}'
            + cta(lang, L(lang, 'cta_general'), L(lang, 'wa_general')) + '</main>')
    page(path, lang, title, t2(data['desc'], lang), body, img=data.get('img'), img_alt=t2(data['alt'], lang) if data.get('img') else '',
         nodes=[crumbs_ld(crumb)] + list(nodes))


def horse_grid(horses, path, lang):
    cards = []
    for h in horses:
        p = rel(path, horse_path(h, lang))
        ph = ''
        if h['img']:
            w, hh = webp_size(h['img'])
            alt = h['alt'] if lang == 'pt' else tr(h['alt'], h['name'])
            ph = f'<span class="ph"><img src="{rel(path, h["img"])}" alt="{E(alt)}" width="{w}" height="{hh}" loading="lazy" decoding="async"></span>'
        tag = f'<em>{L(lang, "role_also")}</em>' if h['also_athlete'] else ''
        text = h['text'] if lang == 'pt' else h.get('text_en') or tr(h['text'], h['name'])
        cards.append(f'<article class="p-card{"" if h["img"] else " noimg"}"><a href="{p}">{ph}<h3>{E(h["name"])}{tag}</h3><span class="ped">{E(h["sire"])} × {E(h["dam"])}</span></a><p>{E(text)}</p></article>')
    return '<div class="p-grid">' + ''.join(cards) + '</div>'


def hub_page(key, lang, title, desc, h1, lede, content, nodes=()):
    idx = LANGS.index(lang)
    path = HUBS[key][idx]
    crumb = [(L(lang, 'nav_home'), HUBS['home'][idx]), (L(lang, 'nav_' + key), path)]
    body = (f'<main>{crumbs_html(path, crumb)}<header class="n-head wrap pad" style="padding-top:clamp(24px,4vh,48px)"><span class="label">{L(lang, "nav_" + key)}</span><h1>{E(h1)}</h1><p>{E(lede)}</p></header>'
            f'<div class="wrap pad p-hub">{content(path)}</div>' + cta(lang, L(lang, 'cta_general'), L(lang, 'wa_general')) + '</main>')
    page(path, lang, title, desc, body, nodes=[crumbs_ld(crumb), {'@type': 'CollectionPage', 'name': h1, 'url': url(path), 'inLanguage': HTML_LANG[lang], 'isPartOf': {'@id': BASE + '/#site'}}] + list(nodes))


def build_hubs():
    mares = [h for h in HORSES.values() if h['section'] == 'mares']
    athletes = [h for h in HORSES.values() if h['section'] == 'athletes' and not h.get('extra')]
    extras = [h for h in HORSES.values() if h.get('extra')]
    latest = sorted(NEWS, key=lambda n: n['date'], reverse=True)
    for lang in LANGS:
        i = LANGS.index(lang)
        pt = lang == 'pt'
        hub_page('mares', lang,
                 'Matrizes Quarto de Milha do B2B Ranch · Três Rios, RJ' if pt else 'Quarter Horse Broodmares at B2B Ranch, Brazil',
                 'Conheça as éguas matrizes Quarto de Milha do B2B Ranch: importadas, de linhagens raras e algumas ainda em pista, com pedigree e produção.' if pt else 'Meet the Quarter Horse broodmares of B2B Ranch in Brazil: imported mares, rare bloodlines and some still competing, with pedigrees and offspring.',
                 'Matrizes Quarto de Milha do B2B Ranch' if pt else 'Quarter Horse broodmares at B2B Ranch',
                 'As éguas que formam cada geração do B2B Ranch, em Três Rios (RJ): importadas, de linhagens raras, e algumas ainda em pista nos Três Tambores.' if pt else 'The mares behind every generation at B2B Ranch in Três Rios, Rio de Janeiro: imported, from rare bloodlines, and some still competing in barrel racing.',
                 lambda path, l=lang: horse_grid(mares, path, l))
        hub_page('athletes', lang,
                 'Atletas de Três Tambores da criação B2B Ranch' if pt else 'Barrel Racing Athletes Bred by B2B Ranch',
                 'Atletas da criação B2B Ranch nos Três Tambores e Seis Balizas: pedigree, tempos e resultados publicados de cada cavalo.' if pt else 'Quarter Horse athletes bred by B2B Ranch in barrel racing and pole bending: pedigrees, times and published results for each horse.',
                 'Atletas da criação B2B Ranch' if pt else 'Athletes bred by B2B Ranch',
                 'A genética B2B medida em segundos, nas principais provas de Três Tambores e Seis Balizas do Brasil.' if pt else 'B2B genetics measured in seconds, at the main barrel racing and pole bending events in Brazil.',
                 lambda path, l=lang: horse_grid(athletes, path, l) + f'<h2 class="p-sub">{L(l, "extras_h")}</h2>' + horse_grid(extras, path, l))
        stall = [('Tux N Rolls', 'tux-n-rolls', 'assets/tux-profile.webp', 'First Down Dash × Zevis Doll · 1999–2023',
                  ('A base do B2B Ranch: 7.672 pontos ABQM e R$ 5.018.420,75 em ganhos dos filhos pelo SGP Três Tambores. Pai de B2B Lovergirl Rolls, única tríplice coroada do Brasil.',
                   'The foundation of B2B Ranch: 7,672 ABQM points and R$ 5,018,420.75 in offspring earnings on the SGP barrel racing record. Sire of B2B Lovergirl Rolls, the only Triple Crown winner in Brazil.')),
                 ('B2B Lucius Ta Fame', 'lucius-ta-fame', 'assets/lucius-retrato.webp', 'Tux N Rolls × KR The Black Pearl · 2012',
                  ('Nascido e criado no B2B Ranch. Pai de B2B Brave Rolls, Top 3 na final do Potro do Futuro ABQM 2026, e de B2B Aphrodite Rolls, com menor tempo de 16.671.',
                   'Born and raised at B2B Ranch. Sire of B2B Brave Rolls, Top 3 at the 2026 ABQM Potro do Futuro final, and of B2B Aphrodite Rolls, with a best time of 16.671.')),
                 ('Adios Pantalones', 'adios-pantalones', 'assets/adios-perfil.webp', 'Tres Seis × French Bar Belle · 2020',
                  ('Primeiro e único garanhão a passar de US$ 1 milhão em ganhos nos Três Tambores. Genética no Brasil pelo Condomínio Adios Pantalones, do qual o B2B Ranch faz parte.',
                   'The first and only stallion to pass US$1 million in barrel racing earnings. His genetics reach Brazil through the Adios Pantalones syndicate, of which B2B Ranch is a member.'))]
        def stall_html(path, l=lang):
            out = []
            for n, s, im, ped, tx in stall:
                w, hh = webp_size(im)
                out.append(f'<article class="p-card wide"><a href="{rel(path, SECTIONS["stallions"][LANGS.index(l)] + "/" + s + ".html")}"><span class="ph"><img src="{rel(path, im)}" alt="{E(n)}" width="{w}" height="{hh}" loading="lazy" decoding="async"></span><h3>{n}</h3><span class="ped">{ped}</span></a><p>{t2(tx, l)}</p></article>')
            return '<div class="p-grid three">' + ''.join(out) + '</div>'
        hub_page('stallions', lang,
                 'Garanhões Quarto de Milha: Tux N Rolls, Lucius e Adios' if pt else 'Quarter Horse Stallions: Tux N Rolls, Lucius, Adios',
                 'Os garanhões por trás da genética B2B: Tux N Rolls, B2B Lucius Ta Fame e Adios Pantalones. Pedigree, números e contato para coberturas.' if pt else 'The stallions behind B2B genetics: Tux N Rolls, B2B Lucius Ta Fame and Adios Pantalones. Pedigrees, records and breeding enquiries.',
                 'Garanhões do B2B Ranch' if pt else 'B2B Ranch stallions',
                 'Os garanhões por trás da genética B2B: a base de toda a criação, o filho que leva a linhagem adiante e um recordista mundial.' if pt else 'The stallions behind B2B genetics: the foundation of the program, the son carrying the line forward, and a world record holder.',
                 stall_html)
        def news_html(path, l=lang):
            out = []
            for year in sorted({n['date'][:4] for n in latest}, reverse=True):
                out.append(f'<h2 class="p-sub">{year}</h2><div class="n-grid">' + ''.join(news_card(n, l, path) for n in latest if n['date'][:4] == year) + '</div>')
            return ''.join(out)
        hub_page('news', lang,
                 'Notícias e resultados do B2B Ranch nos Três Tambores' if pt else 'B2B Ranch News and Barrel Racing Results',
                 'Resultados, passadas e novidades do B2B Ranch nas provas de Três Tambores e Seis Balizas do Brasil, etapa por etapa.' if pt else 'Results and news from B2B Ranch at barrel racing and pole bending events across Brazil, event by event.',
                 'Notícias e resultados' if pt else 'News and results',
                 'Quase todo fim de semana tem prova. Resultados, tempos e novidades do B2B Ranch, de cada etapa.' if pt else 'There is a competition almost every weekend. Results, times and news from B2B Ranch, event by event.',
                 news_html)
        def guides_html(path, l=lang):
            c = [(t2(g['nav'], l), f'{SECTIONS["guides"][LANGS.index(l)]}/{t2(g["slug"], l)}.html', t2(g['desc'], l)) for g in GUIDES]
            c += [(L(l, 'nav_glossary'), HUBS['glossary'][LANGS.index(l)], t2(GLOSSARY['desc'], l)), (L(l, 'nav_faq'), HUBS['faq'][LANGS.index(l)], t2(FAQ['desc'], l))]
            return '<ul class="p-guides">' + ''.join(f'<li><a href="{rel(path, p)}"><b>{E(n)}</b></a><span>{E(d)}</span></li>' for n, p, d in c) + '</ul>'
        hub_page('guides', lang,
                 'Guias: Três Tambores e cavalo Quarto de Milha · B2B Ranch' if pt else 'Guides: Barrel Racing and Quarter Horses · B2B Ranch',
                 'Guias do B2B Ranch sobre Três Tambores, Seis Balizas, Potro do Futuro, a raça Quarto de Milha, reprodução e o vocabulário do meio.' if pt else 'B2B Ranch guides to barrel racing in Brazil, pole bending, the Potro do Futuro, the Quarter Horse breed, reproduction and key terms.',
                 'Guias sobre o Quarto de Milha e os Três Tambores' if pt else 'Guides to Quarter Horses and barrel racing in Brazil',
                 'Explicações diretas sobre as provas, a raça e a criação, para quem está chegando ao meio ou acompanhando de outro país.' if pt else 'Plain explanations of the events, the breed and breeding, for newcomers and for readers following Brazilian competition from abroad.',
                 guides_html)
        def films_html(path, l=lang):
            films = [('1wnK9MEXw0Y', 'assets/institucional-2-poster.webp', ('B2B Ranch, o filme', 'B2B Ranch, the film'), ('Seis minutos sobre o haras, a criação e as pessoas por trás de cada cavalo.', 'Six minutes on the ranch, the breeding program and the people behind every horse.')),
                     ('4IPh_fbGn5g', 'assets/institucional-poster.webp', ('Institucional', 'Institutional film'), ('A equipe, a rotina do haras e os cavalos que levam o nome B2B às pistas.', 'The team, daily life at the ranch and the horses that carry the B2B name into the arena.'))]
            out = ''
            for vid, im, n, d in films:
                w, hh = webp_size(im)
                out += f'<article class="p-card wide"><a href="https://www.youtube.com/watch?v={vid}" target="_blank" rel="noopener"><span class="ph"><img src="{rel(path, im)}" alt="{E(t2(n, l))}" width="{w}" height="{hh}" loading="lazy" decoding="async"></span><h3>{E(t2(n, l))}</h3><span class="ped">{L(l, "watch_yt")}</span></a><p>{E(t2(d, l))}</p></article>'
            return f'<div class="p-grid two">{out}</div>'
        hub_page('films', lang,
                 'Filmes do B2B Ranch: conheça o haras por dentro' if pt else 'B2B Ranch Films: Inside the Ranch in Brazil',
                 'Assista aos filmes do B2B Ranch: o haras em Três Rios (RJ), a criação de cavalos Quarto de Milha e as pessoas por trás de cada cavalo.' if pt else 'Watch the B2B Ranch films: the ranch in Três Rios, Brazil, the Quarter Horse breeding program and the people behind every horse.',
                 'Filmes do B2B Ranch' if pt else 'B2B Ranch films',
                 'Dois filmes sobre o haras, a criação e as pessoas por trás de cada cavalo.' if pt else 'Two films about the ranch, the breeding program and the people behind every horse.',
                 films_html)
        # contact
        path = HUBS['contact'][i]
        crumb = [(L(lang, 'nav_home'), HUBS['home'][i]), (L(lang, 'nav_contact'), path)]
        social_names = ['Instagram · @b2branch', 'Facebook · B2B Ranch', 'YouTube · B2B Ranch', 'TikTok · @b2branch']
        sheet = [(L(lang, 'phone_lbl'), f'<a href="tel:{PHONE_E164}">{PHONE}</a>'), ('E-mail', f'<a href="mailto:{EMAIL}">{EMAIL}</a>'),
                 (L(lang, 'location_lbl'), L(lang, 'nap'))]
        body = (f'<main>{crumbs_html(path, crumb)}<header class="n-head wrap pad" style="padding-top:clamp(24px,4vh,48px)"><span class="label">{L(lang, "nav_contact")}</span><h1>{L(lang, "contact_h1")}</h1><p>{L(lang, "contact_lede")}</p></header>'
                '<div class="wrap pad"><dl class="g-sheet">' + ''.join(f'<div><dt>{k}</dt><dd>{v}</dd></div>' for k, v in sheet) + '</dl>'
                f'<section class="p-links"><h2>{L(lang, "social_h")}</h2><ul>' + ''.join(f'<li><a href="{u}" target="_blank" rel="noopener">{n}</a></li>' for u, n in zip(SOCIAL, social_names)) + '</ul></section></div>'
                + cta(lang, L(lang, 'cta_general'), L(lang, 'wa_general')) + '</main>')
        page(path, lang, L(lang, 'contact_title'), L(lang, 'contact_desc'), body,
             nodes=[crumbs_ld(crumb), {'@type': 'ContactPage', 'url': url(path), 'name': L(lang, 'contact_h1'), 'inLanguage': HTML_LANG[lang], 'about': {'@id': BASE + '/#org'}}])
        # long text pages
        text_page('about', lang, ABOUT)
        text_page('breeding', lang, BREEDING)
        text_page('auctions', lang, AUCTIONS)
        text_page('glossary', lang, GLOSSARY, nodes=[{'@type': 'DefinedTermSet', 'name': t2(GLOSSARY['h1'], lang), 'url': url(HUBS['glossary'][i]), 'inLanguage': HTML_LANG[lang]}])
        qa = {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': t2(q, lang), 'acceptedAnswer': {'@type': 'Answer', 'text': re.sub(r'<[^>]+>', '', t2(a, lang))}} for q, a in FAQ['qa']]}
        faq = dict(FAQ, body=[('dl', FAQ['qa'])])
        text_page('faq', lang, faq, nodes=[qa])


def build_guides():
    for lang in LANGS:
        i = LANGS.index(lang)
        for g in GUIDES:
            path = f'{SECTIONS["guides"][i]}/{t2(g["slug"], lang)}.html'
            title, h1, lede = t2(g['title'], lang), t2(g['h1'], lang), t2(g['lede'], lang)
            crumb = [(L(lang, 'nav_home'), HUBS['home'][i]), (L(lang, 'nav_guides'), HUBS['guides'][i]), (t2(g['nav'], lang), path)]
            w, h = webp_size(g['img'])
            others = [o for o in GUIDES if o is not g]
            more = '<section class="p-links wrap pad"><h2>' + L(lang, 'more_guides') + '</h2><ul>' + ''.join(
                f'<li><a href="{rel(path, SECTIONS["guides"][i] + "/" + t2(o["slug"], lang) + ".html")}">{E(t2(o["nav"], lang))}</a></li>' for o in others) + '</ul></section>'
            body = (f'<main>{crumbs_html(path, crumb)}<article><header class="n-head wrap pad" style="padding-top:clamp(24px,4vh,48px)"><span class="label">{L(lang, "nav_guides")}</span><h1>{E(h1)}</h1><p>{E(lede)}</p></header>'
                    f'<figure class="n-hero wrap pad"><img src="{rel(path, g["img"])}" alt="{E(t2(g["alt"], lang))}" width="{w}" height="{h}" fetchpriority="high" style="--pos:50% 40%"></figure>'
                    f'<div class="n-body pad">{rich(g["body"], path, lang)}</div></article>{more}' + cta(lang, L(lang, 'cta_general'), L(lang, 'wa_general')) + '</main>')
            page(path, lang, title, t2(g['desc'], lang), body, img=g['img'], kind='article', img_alt=t2(g['alt'], lang),
                 nodes=[crumbs_ld(crumb), {'@type': 'Article', 'headline': h1[:110], 'description': t2(g['desc'], lang), 'inLanguage': HTML_LANG[lang], 'mainEntityOfPage': url(path), 'image': BASE + '/' + g['img'], 'dateModified': TODAY, 'author': {'@id': BASE + '/#org'}, 'publisher': {'@id': BASE + '/#org'}}])


# ---------- home and stallion pages: Portuguese source -> English page ----------
def is_keep(s):
    s = s.strip()
    if not re.search(r'[A-Za-zÀ-ÿ]', s) or len(s) <= 1 or ' × ' in s or s in KEEP or s.startswith('+55'):
        return True
    return s in HORSES or s in STALLION_FILES


def translate_text(s, ctx):
    core = s.strip()
    unescaped = html.unescape(core)
    if core in T:
        return s.replace(core, E(T[core], quote=False))
    if unescaped in T:
        return s.replace(core, E(T[unescaped], quote=False))
    if is_keep(core):
        return s
    missing.setdefault(unescaped, ctx)
    return s


ATTRS = re.compile(r'\b(alt|aria-label|data-cap|title)="([^"]*)"')


def translate_tag(tag, ctx):
    def sub(m):
        v = translate_text(m.group(2), ctx)
        return f'{m.group(1)}="{v}"'
    tag = ATTRS.sub(sub, tag)
    if re.match(r'<meta (name="description"|property="og:(title|description|image:alt)")', tag):
        tag = re.sub(r'content="([^"]*)"', lambda m: 'content="' + translate_text(m.group(1), ctx) + '"', tag)
    m = re.search(r'href="(https://wa\.me/\d+\?text=)([^"]+)"', tag)
    if m:
        msg = urllib.parse.unquote(m.group(2))
        tag = tag.replace(m.group(0), f'href="{m.group(1)}{urllib.parse.quote(tr(msg, ctx))}"')
    return tag


def relink(doc, src_path, dst_path):
    def fix(val):
        if not val or val.startswith(('http', '#', 'mailto:', 'tel:', 'data:')):
            return val
        p, frag = (val.split('#', 1) + [''])[:2]
        target = posixpath.normpath(posixpath.join(posixpath.dirname(src_path), p))
        target = ROUTES.get(target, target)
        return rel(dst_path, target) + ('#' + frag if frag else '')
    doc = re.sub(r'\b(href|src|poster)="([^"]*)"', lambda m: f'{m.group(1)}="{fix(m.group(2))}"', doc)
    def fix_set(m):
        parts = [x.strip().split() for x in m.group(1).split(',')]
        return 'srcset="' + ', '.join(' '.join([fix(x[0])] + x[1:]) for x in parts) + '"'
    return re.sub(r'\bsrcset="([^"]*)"', fix_set, doc)


GEN = re.compile(r'<!--gen:(\w+)-->.*?<!--/gen:\1-->', re.S)


def gen_regions(path, lang, is_home, title, desc):
    idx = LANGS.index(lang)
    if is_home:
        crumbs = [(L(lang, 'nav_home'), path)]
    else:
        crumbs = [(L(lang, 'nav_home'), HUBS['home'][idx]), (L(lang, 'nav_stallions'), HUBS['stallions'][idx]), (title.split(' · ')[0], path)]
    nodes = [org_ld(), crumbs_ld(crumbs)]
    if is_home:
        nodes.append({'@type': 'WebSite', '@id': BASE + '/#site', 'url': url(path), 'name': 'B2B Ranch', 'inLanguage': HTML_LANG[lang], 'publisher': {'@id': BASE + '/#org'}})
    head = (alt_links(path, lang) + f'\n<meta property="og:locale" content="{OG_LOCALE[lang]}">\n<meta property="og:locale:alternate" content="{OG_LOCALE["en" if lang == "pt" else "pt"]}">\n'
            f'<meta property="og:url" content="{url(path)}">\n' + ld_script(nodes))
    regions = {'head': head, 'foot': foot(path, lang), 'map': sitemap_links(path, lang), 'lang': lang_button(path, lang), 'langjs': LANG_JS, 'top': top(path, lang)}
    regions['hub'] = ('<p class="nw-all">' + ' · '.join(f'<a href="{rel(path, HUBS[k][idx])}">{L(lang, "all_" + k)}</a>' for k in ('mares', 'athletes', 'news')) + '</p>')
    return regions


def fill(doc, regions):
    def sub(m):
        k = m.group(1)
        return f'<!--gen:{k}-->{regions[k]}<!--/gen:{k}-->'
    return GEN.sub(sub, doc)


JS_EN = [('Assistir no YouTube', 'Watch on YouTube'), ('`assets/horse/', '`../assets/horse/')]


def translate_source(src, src_path, dst_path):
    stripped = GEN.sub(lambda m: f'<!--gen:{m.group(1)}--><!--/gen:{m.group(1)}-->', src)
    parts = re.split(r'(<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->)', stripped, flags=re.S)
    out = []
    for part in parts:
        if part.startswith('<script'):
            for a, b in JS_EN:
                part = part.replace(a, b)
            out.append(part)
        elif part.startswith(('<style', '<!--')):
            out.append(part)
        else:
            toks = re.split(r'(<[^>]+>)', part)
            out.append(''.join(translate_tag(x, src_path) if x.startswith('<') else (translate_text(x, src_path) if x.strip() else x) for x in toks))
    doc = ''.join(out).replace('<html lang="pt-BR">', '<html lang="en">')
    return relink(doc, src_path, dst_path)


def build_translated():
    sources = ['index.html'] + [f'garanhoes/{s}.html' for s in STALLION_FILES.values()]
    for sp in sources:
        full = os.path.join(ROOT, sp)
        src = open(full, encoding='utf-8').read()
        title = html.unescape(re.search(r'<title>(.*?)</title>', src).group(1))
        desc = html.unescape(re.search(r'name="description" content="([^"]*)"', src).group(1))
        write(sp, fill(src, gen_regions(sp, 'pt', sp == 'index.html', title, desc)))
        dp = ROUTES[sp]
        en = translate_source(src, sp, dp)
        en_title = html.unescape(re.search(r'<title>(.*?)</title>', en).group(1))
        en_desc = html.unescape(re.search(r'name="description" content="([^"]*)"', en).group(1))
        write(dp, fill(en, gen_regions(dp, 'en', dp == 'en/index.html', en_title, en_desc)))


# ---------- site files ----------
def build_site_files():
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for p in PAGES:
        alt = (f'<xhtml:link rel="alternate" hreflang="pt-BR" href="{url(p["pt"])}"/><xhtml:link rel="alternate" hreflang="en" href="{url(p["en"])}"/>'
               f'<xhtml:link rel="alternate" hreflang="x-default" href="{url(p["pt"])}"/>')
        for k in LANGS:
            lines.append(f'  <url><loc>{url(p[k])}</loc><lastmod>{TODAY}</lastmod>{alt}</url>')
    lines.append('</urlset>\n')
    write('sitemap.xml', '\n'.join(lines))
    write('robots.txt', f'User-agent: *\nAllow: /\nDisallow: /tools/\n\nSitemap: {BASE}/sitemap.xml\n')
    # 301s from the old WordPress addresses; used by Apache/LiteSpeed hosts such as Hostinger, ignored elsewhere
    ht = ['# Old WordPress addresses -> new pages', 'RedirectMatch 404 ^/tools/']
    for old, new in OLD_URLS.items():
        ht.append(f'Redirect 301 /{old}/ /{new}')
    ht.append('ErrorDocument 404 /404.html\n')
    write('.htaccess', '\n'.join(ht))
    # plain-text summary for AI assistants
    llms = ['# B2B Ranch', '', '> B2B Ranch is a Quarter Horse breeding and training ranch in Três Rios, Rio de Janeiro, Brazil, focused on barrel racing (Três Tambores). Founded by Odilon and Maria Izabel (Bebel) Diniz.', '',
            f'Phone and WhatsApp: {PHONE}', f'Email: {EMAIL}', f'Languages: Portuguese ({BASE}/), English ({BASE}/en/)', '', '## Stallions (English)']
    llms += [f'- [{n}]({url(name_path(n, "en"))})' for n in STALLION_FILES]
    llms += ['', '## Key pages (English)'] + [f'- [{L("en", "nav_" + k)}]({url(HUBS[k][1])})' for k in ('about', 'mares', 'athletes', 'news', 'guides', 'breeding', 'auctions', 'faq', 'contact')]
    llms += ['', '## Páginas principais (português)'] + [f'- [{L("pt", "nav_" + k)}]({url(HUBS[k][0])})' for k in ('about', 'stallions', 'mares', 'athletes', 'news', 'guides', 'breeding', 'auctions', 'faq', 'contact')]
    llms += ['', '## Guides (English)'] + [f'- [{g["nav"][1]}]({BASE}/en/guides/{g["slug"][1]}.html)' for g in GUIDES] + ['']
    write('llms.txt', '\n'.join(llms))
    write('404.html', ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Página não encontrada · Page not found · B2B Ranch</title><meta name="robots" content="noindex">'
                       '<base href="/"><link rel="icon" href="assets/logo.webp"><link rel="stylesheet" href="assets/garanhao.css"><link rel="stylesheet" href="assets/noticia.css"></head><body><main class="n-head wrap pad"><img src="assets/logo-mark.webp" alt="B2B Ranch" width="186" height="120"><h1>Página não encontrada</h1><p><a href="index.html">Voltar ao início</a></p><h2 lang="en">Page not found</h2><p lang="en"><a href="en/index.html">Back to the home page</a></p></main></body></html>\n'))


# ---------- checks ----------
PT_WORDS = re.compile(r'\b(égua|éguas|garanhão|garanhões|filha|filho|filhos|mãe|pai|irmã|irmão|matriz|matrizes|tríplice|lugar|prova|provas|pista|notícias|genética|criação|haras|cavalo|cavalos|fale|conhecer|fechar|deslize)\b', re.I)


def check():
    errs = []
    titles, descs = {}, {}
    for path, doc in written.items():
        if not path.endswith('.html') or path == '404.html':
            continue
        # strip the comments/scripts so we only look at real markup
        clean = re.sub(r'(?s)<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->', '', doc)
        for attr, val in re.findall(r'\b(href|src|poster)="([^"]+)"', clean):
            if val.startswith(('http', 'mailto:', 'tel:', '#', 'data:')):
                continue
            target = posixpath.normpath(posixpath.join(posixpath.dirname(path), val.split('#')[0]))
            if not os.path.exists(os.path.join(ROOT, target)):
                errs.append(f'{path}: broken {attr} {val}')
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', doc, re.S):
            json.loads(block)
        t = re.search(r'<title>(.*?)</title>', doc).group(1)
        d = re.search(r'name="description" content="([^"]*)"', doc)
        if t in titles:
            errs.append(f'duplicate title: {t} ({path}, {titles[t]})')
        titles[t] = path
        if not d:
            errs.append(f'{path}: no description')
        elif d.group(1) in descs:
            errs.append(f'duplicate description ({path}, {descs[d.group(1)]})')
        else:
            descs[d.group(1)] = path
        if len(html.unescape(t)) > 75:
            errs.append(f'{path}: long title ({len(html.unescape(t))}): {t}')
        if len(re.findall(r'<h1\b', clean)) != 1:
            errs.append(f'{path}: {len(re.findall(r"<h1", clean))} h1s')
        if path.startswith('en/') and path not in ('en/glossary.html', 'en/guides.html'):  # these two teach the Portuguese terms
            text = re.sub(r'<[^>]+>', ' ', re.sub(r'(?s)<head>.*?</head>', '', clean))
            hits = set(m.group(0).lower() for m in PT_WORDS.finditer(text))
            hits -= {'haras', 'prova'}  # proper names such as Haras Zopone
            if hits:
                errs.append(f'{path}: Portuguese left: {sorted(hits)}')
    return errs


missing, problems = {}, []


def main():
    HORSES.update(parse_home_horses())
    for k, (pt, en) in HUBS.items():
        register(pt, en)
    for s in STALLION_FILES.values():
        register(f'garanhoes/{s}.html', f'en/stallions/{s}.html')
    for h in HORSES.values():
        register(horse_path(h, 'pt'), horse_path(h, 'en'))
    for n in NEWS:
        register(news_path(n, 'pt'), news_path(n, 'en'))
    for g in GUIDES:
        register(f'guias/{g["slug"][0]}.html', f'en/guides/{g["slug"][1]}.html')
    results = result_rows()
    unknown = sorted({h for h in results if h not in HORSES and h not in STALLION_FILES})
    build_translated()
    build_news()
    build_guides()
    build_hubs()
    for h in HORSES.values():
        build_horse(h, results)
    if missing:
        print(f'MISSING TRANSLATIONS ({len(missing)}):')
        for k, c in missing.items():
            print(f'  [{c}] {k!r}')
        sys.exit(1)
    build_site_files()
    errs = check() + problems
    print(f'{len(written)} files written, {len(PAGES)} pages per language.')
    print(f'{len(unknown)} horses appear in results without their own page: {", ".join(unknown)}')
    if errs:
        print(f'{len(errs)} PROBLEMS:')
        for e in errs:
            print(' ', e)
        sys.exit(1)
    print('All checks passed.')


main()
