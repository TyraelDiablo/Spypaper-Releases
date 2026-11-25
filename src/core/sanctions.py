"""Uyarı ve ceza kaydı (sicil): uyarı, atma, ban, süreli ban ve ban kaldırma nedenleriyle profilde saklanır.

Süreli banlar Spypaper açıkken süresi dolunca 'pardon' komutuyla kaldırılır (sunucu kapalıysa açıldığında).
"""
from datetime import datetime, timedelta

KINDS = ("warn", "kick", "ban", "tempban", "pardon")
DURATIONS = [(0, "Kalıcı"), (3600, "1 saat"), (6 * 3600, "6 saat"), (86400, "1 gün"), (3 * 86400, "3 gün"),
             (7 * 86400, "7 gün"), (30 * 86400, "30 gün")]
MAX_ENTRIES = 2000


def _clean(text):
    return " ".join(str(text or "").replace("\n", " ").split())[:200]


class Sanctions:
    def __init__(self, config, server):
        self.config, self.server = config, server

    def entries(self):
        return list(self.config.get("sanctions") or [])

    def _save(self, lst):
        self.config.set("sanctions", lst[-MAX_ENTRIES:])

    def record(self, kind, player, reason="", seconds=0, now=None):
        now = now or datetime.now()
        e = {"kind": kind, "player": player, "reason": _clean(reason), "at": now.isoformat(timespec="seconds")}
        if kind == "tempban":
            e["until"] = (now + timedelta(seconds=seconds)).isoformat(timespec="seconds")
            e["active"] = True
        lst = self.entries()
        if kind == "pardon":                     # elle ban kaldırılınca bekleyen süreli ban da biter
            for x in lst:
                if x.get("kind") == "tempban" and x.get("active") and x["player"].lower() == player.lower():
                    x["active"] = False
        lst.append(e)
        self._save(lst)
        return e

    def commands(self, kind, player, reason=""):
        """Sunucuya gönderilecek komutlar."""
        r = _clean(reason)
        if kind == "warn":
            return [f"tellraw {player} " + _tellraw(r)]
        if kind == "kick":
            return [f"kick {player} {r}".rstrip()]
        if kind in ("ban", "tempban"):
            return [f"ban {player} {r}".rstrip()]
        if kind == "pardon":
            return [f"pardon {player}"]
        return []

    def for_player(self, player):
        low = player.lower()
        return [e for e in self.entries() if e["player"].lower() == low]

    def warn_count(self, player):
        return sum(1 for e in self.for_player(player) if e["kind"] == "warn")

    def due(self, now=None):
        now = now or datetime.now()
        out = []
        for e in self.entries():
            if e.get("kind") == "tempban" and e.get("active"):
                try:
                    if datetime.fromisoformat(e["until"]) <= now:
                        out.append(e)
                except (KeyError, ValueError):
                    pass
        return out

    def tick(self, now=None):
        """Süresi dolan süreli banları kaldırır (sunucu açıksa). Kaldırılan oyuncu adlarını döndürür."""
        if not self.server.is_running:
            return []
        due = self.due(now)
        if not due:
            return []
        names = []
        lst = self.entries()
        for e in lst:
            if e in due:
                e["active"] = False
                e["expired"] = True
                try:
                    self.server.try_send(f"pardon {e['player']}")
                except Exception:
                    pass
                names.append(e["player"])
        for n in names:
            lst.append({"kind": "pardon", "player": n, "reason": "auto", "at": (now or datetime.now()).isoformat(timespec="seconds")})
        self._save(lst)
        return names


def _tellraw(reason):
    import json
    return json.dumps([{"text": "⚠ ", "color": "gold"}, {"text": reason or "Uyarı", "color": "yellow"}], ensure_ascii=False)
