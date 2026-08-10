"""Multi-provider AI hub.

The client configures OpenAI / Anthropic / Azure OpenAI keys in Administration.
Calls go to the default enabled provider; on failure the hub falls through to
the next enabled provider, and finally to the deterministic offline engine, so
the console never breaks.
"""
from __future__ import annotations

from . import db

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-opus-5",
    "azure": "gpt-4o-mini",          # deployment name for Azure
}


def _call_openai(p, system, prompt, max_tokens):
    from openai import OpenAI
    client = OpenAI(api_key=p["api_key"], base_url=p.get("endpoint") or None, timeout=60)
    r = client.chat.completions.create(
        model=p.get("model") or DEFAULT_MODELS["openai"],
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}])
    return r.choices[0].message.content


def _call_anthropic(p, system, prompt, max_tokens):
    import anthropic
    client = anthropic.Anthropic(api_key=p["api_key"], timeout=60)
    r = client.messages.create(
        model=p.get("model") or DEFAULT_MODELS["anthropic"],
        max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}])
    if getattr(r, "stop_reason", None) == "refusal":
        raise RuntimeError("refusal")
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


def _call_azure(p, system, prompt, max_tokens):
    from openai import AzureOpenAI
    client = AzureOpenAI(api_key=p["api_key"], azure_endpoint=p["endpoint"],
                         api_version="2024-06-01", timeout=60)
    r = client.chat.completions.create(
        model=p.get("model") or DEFAULT_MODELS["azure"],
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}])
    return r.choices[0].message.content


_CALLERS = {"openai": _call_openai, "anthropic": _call_anthropic, "azure": _call_azure}


class AIHub:
    def __init__(self):
        self.last_provider = "offline"
        self.last_error: str | None = None

    def status(self):
        prov = db.default_provider()
        return {
            "mode": prov["provider"] if prov else "offline",
            "model": (prov.get("model") or DEFAULT_MODELS.get(prov["provider"], "")) if prov else None,
            "last_used": self.last_provider,
            "last_error": self.last_error,
        }

    def complete(self, system: str, prompt: str, max_tokens: int = 1800,
                 feature: str = "generic") -> tuple[str | None, str]:
        """Returns (text, provider_name). text=None means use offline fallback."""
        import time as _time
        tried = set()
        prov = db.default_provider()
        chain = []
        if prov:
            chain.append(prov)
        for p in (db.list_providers(mask=False) or []):
            if p["provider"] not in {c["provider"] for c in chain} and p["configured"] and p["enabled"]:
                chain.append(p)
        for p in chain:
            if p["provider"] in tried:
                continue
            tried.add(p["provider"])
            t0 = _time.time()
            try:
                text = _CALLERS[p["provider"]](p, system, prompt, max_tokens)
                if text:
                    self.last_provider = p["provider"]
                    self.last_error = None
                    try:
                        db.log_ai_usage(p["provider"], p.get("model") or DEFAULT_MODELS[p["provider"]],
                                        feature, len(system) + len(prompt), len(text),
                                        int((_time.time() - t0) * 1000), "success")
                    except Exception:
                        pass
                    return text, p["provider"]
            except Exception as e:
                self.last_error = f"{p['provider']}: {str(e)[:200]}"
                try:
                    db.log_ai_usage(p["provider"], p.get("model") or "", feature,
                                    len(system) + len(prompt), 0,
                                    int((_time.time() - t0) * 1000), "failed")
                except Exception:
                    pass
        self.last_provider = "offline"
        return None, "offline"

    def test(self, provider: str) -> dict:
        p = db.get_provider(provider)
        if not p or not p.get("api_key"):
            return {"ok": False, "error": "No API key configured"}
        try:
            text = _CALLERS[provider](p, "You are a health check.", "Reply with exactly: OK", 10)
            ok = bool(text)
            db.record_provider_test(provider, "passed" if ok else "failed")
            return {"ok": ok, "response": (text or "")[:50]}
        except Exception as e:
            db.record_provider_test(provider, "failed")
            return {"ok": False, "error": str(e)[:300]}


HUB = AIHub()
