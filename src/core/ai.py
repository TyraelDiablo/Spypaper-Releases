"""Yapay zeka sağlayıcıları (Esplora).

Ayarlar config.json -> "ai":
  provider : "anthropic" | "gemini" | "openai"   (openai = OpenAI ve uyumlu servisler: OpenRouter, LM Studio, Ollama…)
  model    : model adı
  base_url : yalnızca openai uyumlu servisler için (boşsa https://api.openai.com/v1)
  key      : şifreli API anahtarı (core.secrets)
"""
import json
import re
import urllib.error
import urllib.request

from .config import N_
from .secrets import protect, unprotect

PROVIDERS = {
    "anthropic": {"name": "Anthropic (Claude)", "model": "claude-sonnet-5-5"},
    "gemini": {"name": "Google Gemini", "model": "gemini-3.8-flash"},
    "openai": {"name": "OpenAI / uyumlu", "model": "gpt-4o-mini"},
}


class AIError(Exception):
    def __init__(self, template, suggest=None, **kw):
        self.template, self.kw = template, kw
        self.suggest = suggest          # servis başka bir model önerdiyse (ör. eski model kapatıldı)
        super().__init__(template.format(**kw) if kw else template)


def get_cfg(settings):
    c = dict(settings.get("ai") or {})
    c.setdefault("provider", "anthropic")
    c.setdefault("model", PROVIDERS[c["provider"]]["model"])
    c.setdefault("base_url", "")
    c.setdefault("key", "")
    return c


def save_cfg(settings, provider, model, base_url, api_key=None):
    c = get_cfg(settings)
    c.update(provider=provider, model=model.strip(), base_url=base_url.strip())
    if api_key is not None:
        c["key"] = protect(api_key.strip())
    settings.set("ai", c)


def api_key(cfg):
    return unprotect(cfg.get("key", ""))


def _post(url, headers, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
            msg = (detail.get("error") or {}).get("message") if isinstance(detail.get("error"), dict) \
                else detail.get("error") or detail.get("message")
        except Exception:
            msg = ""
        if e.code in (401, 403):
            raise AIError(N_("API anahtarı geçersiz ya da yetkisiz ({code})."), code=e.code)
        m = re.search(r"use (?:models/)?([A-Za-z0-9._\-]+) for", msg or "")
        if e.code in (400, 404) and m:
            raise AIError(N_("Yapay zeka hatası {code}: {msg}"), suggest=m.group(1), code=e.code, msg=msg)
        if e.code == 429:
            raise AIError(N_("İstek sınırına ulaşıldı (429). Biraz sonra tekrar dene."))
        raise AIError(N_("Yapay zeka hatası {code}: {msg}"), code=e.code, msg=msg or e.reason)
    except Exception as e:
        raise AIError(N_("Yapay zeka servisine bağlanılamadı: {e}"), e=e)


def chat(cfg, system, messages, max_tokens=1500, temperature=0.4):
    """messages: [{"role": "user"|"assistant", "content": str}] -> yanıt metni."""
    key = api_key(cfg)
    if not key and cfg["provider"] in ("anthropic", "gemini"):
        raise AIError(N_("API anahtarı ayarlanmamış. ☰ menüsünden Yapay Zeka Ayarları'nı aç."))
    if cfg["provider"] == "anthropic":
        data = _post("https://api.anthropic.com/v1/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"model": cfg["model"], "max_tokens": max_tokens, "temperature": temperature,
                      "system": system, "messages": messages})
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    if cfg["provider"] == "gemini":
        # Gemini: rol adları "user" / "model"; sistem promptu ayrı alanda
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in messages]
        data = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['model']}:generateContent",
                     {"x-goog-api-key": key},
                     {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                      # düşünen modeller düşünme jetonlarını da bu sınırdan harcar
                      "generationConfig": {"maxOutputTokens": max(max_tokens * 3, 2048), "temperature": temperature}})
        try:
            cand = data["candidates"][0]
        except (KeyError, IndexError, TypeError):
            reason = (data.get("promptFeedback") or {}).get("blockReason", "")
            raise AIError(N_("Gemini yanıt vermedi: {e}"), e=reason or "?")
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
        if not text:
            raise AIError(N_("Gemini yanıt vermedi: {e}"), e=cand.get("finishReason", "?"))
        return text.strip()
    base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    data = _post(f"{base}/chat/completions", headers,
                 {"model": cfg["model"], "max_tokens": max_tokens, "temperature": temperature,
                  "messages": [{"role": "system", "content": system}] + messages})
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        raise AIError(N_("Beklenmeyen yanıt biçimi."))


def chat_auto(settings, system, messages, **kw):
    """chat() + servis eski modeli kapatıp yenisini önerirse modeli otomatik günceller ve bir kez yeniden dener.
    (yanıt, değiştiyse_yeni_model) döndürür."""
    cfg = get_cfg(settings)
    try:
        return chat(cfg, system, messages, **kw), None
    except AIError as e:
        if not e.suggest or e.suggest == cfg["model"]:
            raise
        cfg["model"] = e.suggest
        out = chat(cfg, system, messages, **kw)
        c = get_cfg(settings)
        c["model"] = e.suggest
        settings.set("ai", c)
        return out, e.suggest


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise AIError(N_("API anahtarı geçersiz ya da yetkisiz ({code})."), code=e.code)
        raise AIError(N_("Yapay zeka hatası {code}: {msg}"), code=e.code, msg=e.reason)
    except Exception as e:
        raise AIError(N_("Yapay zeka servisine bağlanılamadı: {e}"), e=e)


def list_models(cfg):
    """Sağlayıcının bu anahtarla kullanılabilen sohbet modelleri (yeniden eskiye/alfabetik)."""
    key = api_key(cfg)
    if cfg["provider"] == "anthropic":
        data = _get("https://api.anthropic.com/v1/models?limit=100",
                    {"x-api-key": key, "anthropic-version": "2023-06-01"})
        return [m["id"] for m in data.get("data", [])]
    if cfg["provider"] == "gemini":
        out, token = [], ""
        for _ in range(5):
            data = _get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"
                        + (f"&pageToken={token}" if token else ""), {"x-goog-api-key": key})
            for m in data.get("models", []):
                if "generateContent" in m.get("supportedGenerationMethods", []):
                    out.append(m["name"].removeprefix("models/"))
            token = data.get("nextPageToken")
            if not token:
                break
        # en yeni sürüm önce: gemini-3.8-flash, gemini-3.5-pro, ...
        def k(n):
            v = re.findall(r"\d+(?:\.\d+)?", n)
            return (-float(v[0]) if v else 0, "exp" in n or "preview" in n, n)
        return sorted(out, key=k)
    base = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    data = _get(f"{base}/models", {"Authorization": f"Bearer {key}"} if key else {})
    return sorted(m["id"] for m in data.get("data", []))


def test(settings):
    """Bağlantı testi. Model otomatik değiştiyse yeni modeli döndürür."""
    _, new = chat_auto(settings, "Reply with exactly: OK", [{"role": "user", "content": "ping"}], max_tokens=50)
    return new
