"""Value helpers for the XING parsers: safe nested access, numbers, text,
ISO dates and HTML -> text. Pure functions, no network; every helper
tolerates None and junk.

Same semantics as jobstreet/shared.py (the subset xing uses); the ones every site
shares come from scraper_utils and the rest live here, because the xing package
ships as its own open-source repo, which must not pull in other sites'
modules."""
from datetime import datetime
from html.parser import HTMLParser
from scraper_utils.text import clean as text, html_to_text, multiline
from scraper_utils.dates import iso_date, iso_datetime
from scraper_utils.values import amount, as_dict, as_list, g, num, to_int_round as to_int


_LONG_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")


_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt", "dl"}


_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}
