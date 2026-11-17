"""Esplora sohbet geçmişi: sunucu başına, bu bilgisayarda JSON dosyaları.

Yer: config.json'un yanındaki esplora_chats/<sunucu kimliği>/<sohbet kimliği>.json
Görseller kaydedilmez (yalnızca sayısı kalır); dosyalar küçük kalır ve ekran görüntüleri diske yazılmaz.
Sunucu başına en fazla MAX_CHATS sohbet tutulur; fazlası en eskiden silinir.
"""
import json
import os
import re
import secrets
from datetime import datetime

DIR_NAME = "esplora_chats"
MAX_CHATS = 100
TITLE_LEN = 60
_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


def new_id():
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)


def _safe(name):
    """Sunucu kimliği klasör adı olarak güvenli olsun."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(name or "sunucu"))[:64] or "sunucu"


def title_of(messages):
    for m in messages:
        if m.get("role") == "user" and not m.get("data") and not m.get("cmd") and not m.get("note"):
            text = (m.get("label") or m.get("content") or "").strip()
            if not text and m.get("images"):
                return "[görsel]"
            line = text.splitlines()[0] if text else ""
            return line if len(line) <= TITLE_LEN else line[:TITLE_LEN - 1].rstrip() + "…"
    return ""


def strip_images(messages):
    """Görsel verisini atar, sayısını bırakır: {"mime": ..., "omitted": True}"""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("images"):
            m["images"] = [{"mime": im.get("mime", ""), "omitted": True} for im in m["images"]]
        out.append(m)
    return out


class ChatStore:
    def __init__(self, base_dir, server_id):
        self.dir = os.path.join(base_dir, DIR_NAME, _safe(server_id))

    @classmethod
    def for_profile(cls, profile):
        return cls(os.path.dirname(os.path.abspath(profile.settings.path)), profile.id)

    def _path(self, chat_id):
        if not _ID_RE.match(chat_id or ""):
            raise ValueError("geçersiz sohbet kimliği")
        return os.path.join(self.dir, chat_id + ".json")

    def save(self, chat_id, messages):
        """Sohbeti yazar (boşsa yazmaz). Geçici dosyaya yazıp yerine taşır; yarım dosya kalmaz."""
        msgs = list(messages)
        if not msgs or not title_of(msgs):
            return False
        os.makedirs(self.dir, exist_ok=True)
        path = self._path(chat_id)
        now = datetime.now().isoformat(timespec="seconds")
        created = now
        old = self._read(path)
        if old:
            created = old.get("created") or now
        today = datetime.now().strftime("%Y-%m-%d")
        clean = []
        for m in strip_images(msgs):
            m.setdefault("date", today)
            clean.append(m)
        data = {"id": chat_id, "title": title_of(clean), "created": created, "updated": now, "messages": clean}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
        self.prune()
        return True

    @staticmethod
    def _read(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) and isinstance(data.get("messages"), list) else None
        except (OSError, ValueError):
            return None

    def list(self):
        """[{id, title, created, updated, count}] — en yeni önce."""
        out = []
        if not os.path.isdir(self.dir):
            return out
        for name in os.listdir(self.dir):
            if not name.endswith(".json") or not _ID_RE.match(name[:-5]):
                continue
            data = self._read(os.path.join(self.dir, name))
            if not data:
                continue
            msgs = data["messages"]
            out.append({"id": name[:-5], "title": data.get("title") or title_of(msgs),
                        "created": data.get("created", ""), "updated": data.get("updated", ""),
                        "count": sum(1 for m in msgs if m.get("role") == "user" and not m.get("data")
                                     and not m.get("cmd") and not m.get("note"))})
        out.sort(key=lambda c: (c["updated"], c["id"]), reverse=True)
        return out

    def load(self, chat_id):
        data = self._read(self._path(chat_id))
        return list(data["messages"]) if data else None

    def delete(self, chat_id):
        try:
            os.remove(self._path(chat_id))
            return True
        except (OSError, ValueError):
            return False

    def delete_all(self):
        n = 0
        for c in self.list():
            n += self.delete(c["id"])
        return n

    def prune(self, keep=MAX_CHATS):
        for c in self.list()[keep:]:
            self.delete(c["id"])
