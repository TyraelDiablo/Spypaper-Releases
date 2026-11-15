"""SoundCloud bağlantısından parça adı ve sanatçı (herkese açık oEmbed, anahtar gerekmez).

SoundCloud'un açık bir indirme API'si yok; akışı kaydetmek hem kurallarına hem telif hakkına aykırı.
Bu yüzden Spypaper yalnızca bilgileri alır ve sayfayı tarayıcıda açar; sanatçı indirmeye izin verdiyse
kullanıcı dosyayı oradan indirip seçer.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .config import N_

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Spypaper"
_URL = re.compile(r"^https?://(?:www\.|m\.|on\.)?soundcloud\.com/[^\s]+$", re.I)


class SoundCloudError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def is_url(text):
    return bool(_URL.match((text or "").strip()))


def clean_url(text):
    u = (text or "").strip()
    if not u.lower().startswith("http"):
        u = "https://" + u
    u = u.split("?")[0].split("#")[0]
    if u.lower().startswith("http://"):
        u = "https://" + u[7:]
    return u.replace("://m.soundcloud.com", "://soundcloud.com")


def parse_oembed(data):
    """oEmbed JSON'undan (başlık, sanatçı)."""
    title = str(data.get("title") or "").strip()
    artist = str(data.get("author_name") or "").strip()
    if artist and title.endswith(" by " + artist):
        title = title[: -len(" by " + artist)].strip()
    return title, artist


def info(url, timeout=15):
    """(başlık, sanatçı, temiz_adres)"""
    if not is_url(url):
        raise SoundCloudError(N_("Bu bir SoundCloud parça bağlantısı değil."))
    url = clean_url(url)
    q = urllib.parse.urlencode({"format": "json", "url": url})
    req = urllib.request.Request(f"https://soundcloud.com/oembed?{q}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(200_000)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            raise SoundCloudError(N_("SoundCloud'da bu parça bulunamadı ya da gizli."))
        raise SoundCloudError(N_("SoundCloud'a ulaşılamadı: {e}"), e=str(e))
    except Exception as e:
        raise SoundCloudError(N_("SoundCloud'a ulaşılamadı: {e}"), e=str(e))
    try:
        title, artist = parse_oembed(json.loads(raw.decode("utf-8", "replace")))
    except ValueError:
        raise SoundCloudError(N_("SoundCloud'dan geçersiz cevap geldi."))
    return title, artist, url
