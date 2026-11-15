"""Newgrounds Audio Portal: ID'den parça adı, sanatçı ve MP3 indirme.

  https://www.newgrounds.com/audio/listen/<id>  sayfasındaki oynatıcı verisinden MP3 adresi
  (audio.ngfiles.com) ve og:title / sanatçı adı okunur.
Parçaların telif hakkı sahiplerine aittir; Spypaper yalnızca kullanıcının verdiği ID'yi indirir ve diske
açıklama olarak sanatçıyı yazar. İndirme kapatılmış parçalar indirilemez.
"""
import html
import json
import re
import urllib.error
import urllib.request

from .config import N_

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Spypaper"
MAX_BYTES = 40 * 1024 * 1024


class NewgroundsError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def _get(url, limit, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise NewgroundsError(N_("Newgrounds'ta bu ID ile parça bulunamadı."))
        raise NewgroundsError(N_("Newgrounds'a ulaşılamadı: {e}"), e=str(e))
    except Exception as e:
        raise NewgroundsError(N_("Newgrounds'a ulaşılamadı: {e}"), e=str(e))
    if len(data) > limit:
        raise NewgroundsError(N_("Parça çok büyük."))
    return data


def parse_page(page):
    """Sayfa HTML'inden (başlık, sanatçı, mp3_adresi)."""
    m = re.search(r'https?:\\?/\\?/audio\.ngfiles\.com\\?/[^"\'\s<>]+?\.mp3[^"\'\s<>]*', page)
    url = m.group(0).replace("\\/", "/") if m else ""
    url = url.split('\\"')[0]
    title = ""
    t = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', page)
    if t:
        title = html.unescape(t.group(1)).strip()
    artist = ""
    a = re.search(r'"artist"\s*:\s*"([^"]{1,80})"', page) or \
        re.search(r'class="item-details-main"[^>]*>\s*<h4>\s*<a[^>]*>([^<]{1,80})</a>', page)
    if a:
        raw = a.group(1)
        try:
            raw = json.loads(f'"{raw}"')                # JSON kaçışları (\u00e7 gibi)
        except ValueError:
            pass
        artist = html.unescape(raw).strip()
    return title, artist, url


def fetch(song_id):
    """(başlık, sanatçı, mp3_baytları)"""
    sid = str(song_id).strip()
    if not sid.isdigit() or len(sid) > 9:
        raise NewgroundsError(N_("Newgrounds ID yalnızca rakamlardan oluşur."))
    page = _get(f"https://www.newgrounds.com/audio/listen/{sid}", 3_000_000).decode("utf-8", "replace")
    title, artist, url = parse_page(page)
    if not url:
        raise NewgroundsError(N_("Bu parça indirilemiyor (sanatçı indirmeyi kapatmış olabilir). Ses dosyasını elle seçebilirsin."))
    if not url.startswith("https://audio.ngfiles.com/"):
        url = "https://" + url.split("://", 1)[-1]
        if not url.startswith("https://audio.ngfiles.com/"):
            raise NewgroundsError(N_("Güvenilmeyen indirme adresi: {url}"), url=url[:80])
    data = _get(url, MAX_BYTES, timeout=60)
    return title or f"Newgrounds #{sid}", artist, data
