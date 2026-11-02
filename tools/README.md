# Building the site

Run `python3 tools/build.py` after any change, then publish everything it writes.

- Edit Portuguese directly in `index.html` and `garanhoes/*.html`. Leave the `<!--gen:...-->` regions alone.
- Add the English for changed text in `content_i18n.py`. The build stops and lists anything missing.
- Add news in `content_news.py`, extra horses in `content_horses.py`, guides and long pages in `content_guides.py`.
- Mares and athletes come from the lists on the home page, so a new horse there gets its own page in both languages.
- Do not edit `en/`, `matrizes/`, `atletas/`, `noticias/`, `guias/`, the hub pages or `sitemap.xml` by hand: the build overwrites them.

The build also checks links, duplicate titles and descriptions, one H1 per page, valid structured data and leftover Portuguese in English pages.
