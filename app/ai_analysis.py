"""
AI-powered document change analysis using local Ollama LLM or Claude API.
Generates a professional Issue List from redline changes, structured
in sections with traffic-light severity ratings, like M&A transaction issue lists.
"""
import json
import os
import re
import requests
from typing import List, Dict, Any

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:14b"
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MODELS = {
    "claude-sonnet-4-20250514": "Claude Sonnet 4 (Empfohlen)",
    "claude-opus-4-20250514": "Claude Opus 4 (Premium)",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5 (Schnell)",
}

# Persistent config file for API key (stored next to the database)
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, '..', '.api_config.json')


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_config(cfg: dict):
    with open(_CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)


def set_api_key(key: str):
    """Store the Anthropic API key persistently."""
    cfg = _load_config()
    cfg["anthropic_api_key"] = key.strip()
    _save_config(cfg)


def get_api_key() -> str:
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if env_key:
        return env_key
    cfg = _load_config()
    return cfg.get("anthropic_api_key", "")


def _check_ollama():
    """Check if Ollama is running and reachable."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = r.json().get("models", [])
            return True, [m["name"] for m in models]
        return False, []
    except Exception:
        return False, []


def _check_claude():
    """Check if Claude API key is configured and valid."""
    key = get_api_key()
    if not key:
        return False, "Kein API-Key konfiguriert"
    if not key.startswith("sk-ant-"):
        return False, "Ungültiges API-Key Format"
    return True, "OK"


def get_providers_status():
    """Return status of all available AI providers."""
    ollama_ok, ollama_models = _check_ollama()
    claude_ok, claude_msg = _check_claude()
    return {
        "ollama": {
            "available": ollama_ok,
            "models": ollama_models,
            "default_model": DEFAULT_MODEL,
        },
        "claude": {
            "available": claude_ok,
            "message": claude_msg if not claude_ok else "Verbunden",
            "models": list(CLAUDE_MODELS.keys()),
            "model_names": CLAUDE_MODELS,
            "default_model": CLAUDE_DEFAULT_MODEL,
            "has_key": bool(get_api_key()),
        },
    }


def _build_prompt(changes: List[Dict], client_party: str,
                  document_context: str = "", client_version: str = "a",
                  provider: str = "ollama") -> str:
    """Build the analysis prompt for structured JSON output."""
    changes_text = []
    for i, ch in enumerate(changes, 1):
        ch_type = ch.get("type", "unbekannt")
        old = ch.get("old", "")
        new = ch.get("new", "")
        para = ch.get("para", 0)

        if ch_type in ("Einfügung", "Eingefügt"):
            changes_text.append(f"{i}. EINGEFÜGT (Absatz {para}): \"{new}\"")
        elif ch_type in ("Löschung", "Gelöscht"):
            changes_text.append(f"{i}. GELÖSCHT (Absatz {para}): \"{old}\"")
        elif ch_type in ("Ersetzung", "Geändert"):
            changes_text.append(f"{i}. GEÄNDERT (Absatz {para}): \"{old}\" → \"{new}\"")
        elif "Verschoben" in ch_type:
            changes_text.append(f"{i}. VERSCHOBEN (Absatz {para}): \"{old or new}\"")
        else:
            changes_text.append(f"{i}. {ch_type} (Absatz {para}): \"{old}\" → \"{new}\"")

    changes_block = "\n".join(changes_text)

    if client_version == "a":
        perspective = (
            f"Version A (alt) ist das Dokument deines Mandanten ({client_party}). "
            f"Version B (neu) enthält die Änderungen der Gegenseite."
        )
    else:
        perspective = (
            f"Version B (neu) ist das Dokument deines Mandanten ({client_party}). "
            f"Version A (alt) ist das Dokument der Gegenseite."
        )

    doc_ctx = f"\nDokumenttyp: {document_context}" if document_context else ""

    prompt = f"""Du bist ein erfahrener deutscher Wirtschaftsanwalt und erstellst eine professionelle Issue List für eine Vertragsverhandlung.

Mandant: {client_party}
{perspective}{doc_ctx}

ÄNDERUNGEN (Version A → Version B):
{changes_block}

Erstelle eine strukturierte Issue List als JSON. Gruppiere die Änderungen in thematische Abschnitte (z.B. "Definitionen", "Kaufpreis", "Garantien", "Haftung", etc.).

Antworte NUR mit validem JSON in exakt diesem Format:
{{
  "title": "ISSUE LIST — {document_context or 'Vertrag'}",
  "subtitle": "Mandant: {client_party}",
  "sections": [
    {{
      "number": "I",
      "title": "ABSCHNITTSTITEL IN GROSSBUCHSTABEN",
      "summary": "Kurze Zusammenfassung der Änderungen in diesem Abschnitt (1-2 Sätze)",
      "issues": [
        {{
          "ref": "1.1",
          "label": "Kurzer Bezeichner (z.B. Definition 'Parteien')",
          "issue": "Beschreibung der Änderung und ihrer Bedeutung. Was wurde geändert und warum ist das relevant?",
          "old_text": "Originaltext aus Version A (kurz, max 100 Zeichen)",
          "new_text": "Neuer Text aus Version B (kurz, max 100 Zeichen)",
          "severity": "KRITISCH",
          "recommendation": "Ablehnen / Nachverhandeln / Akzeptieren / Gegenvorschlag",
          "comment": "Konkreter Kommentar und Handlungsempfehlung für den Mandanten"
        }}
      ]
    }}
  ],
  "executive_summary": {{
    "total_issues": 0,
    "critical": 0,
    "important": 0,
    "neutral": 0,
    "favorable": 0,
    "key_risks": ["Risiko 1", "Risiko 2"],
    "strategy": "Empfohlene Verhandlungsstrategie in 2-3 Sätzen"
  }}
}}

Regeln:
- severity: Nur "KRITISCH", "WICHTIG", "NEUTRAL" oder "VORTEILHAFT"
- JEDE einzelne Änderung MUSS als eigenes Issue erfasst werden — KEINE Änderung auslassen
- Erstelle so viele Abschnitte und Issues wie nötig — 50, 100 oder 200 Issues sind völlig normal
- NICHT zusammenfassen: Jede Änderung = ein separates Issue mit eigenem Ref, eigener Bewertung
- Kategorien: rechtliche Issues, wirtschaftliche Issues, finanzielle Issues, Haftungsrisiken, Definitionen, Verfahrensfragen
- old_text und new_text: Gib den relevanten Originaltext an (nicht nur zusammenfassen)
- Bewerte aus Sicht von {client_party}
- Sei präzise und praxisorientiert
- Antworte auf Deutsch
- NUR valides JSON, keine Erklärungen davor oder danach"""

    return prompt


def _parse_json_response(text: str) -> Dict:
    """Try to extract JSON from LLM response, handling common issues."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in markdown code fences
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find first { to last }
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _build_result(raw_text: str, use_model: str, changes: List[Dict],
                  client_party: str, provider: str) -> Dict[str, Any]:
    """Parse LLM response and build result dict."""
    parsed = _parse_json_response(raw_text)

    if parsed and "sections" in parsed:
        return {
            "status": "ok",
            "structured": True,
            "issue_list": parsed,
            "raw": raw_text,
            "model": use_model,
            "provider": provider,
            "change_count": len(changes),
            "client_party": client_party,
        }
    else:
        return {
            "status": "ok",
            "structured": False,
            "analysis": raw_text,
            "model": use_model,
            "provider": provider,
            "change_count": len(changes),
            "client_party": client_party,
        }


def _call_claude_api(api_key: str, model: str, prompt: str, max_tokens: int = 16384) -> Dict:
    """Make a single Claude API call. Returns parsed response or error dict."""
    try:
        response = requests.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
            },
            timeout=300,
        )

        if response.status_code == 401:
            return {"error": "Ungültiger API-Key. Bitte prüfen Sie Ihren Anthropic API-Key."}
        if response.status_code == 429:
            import time
            time.sleep(5)
            # Retry once
            response = requests.post(
                CLAUDE_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=300,
            )
            if response.status_code != 200:
                return {"error": "Rate Limit erreicht. Bitte warten Sie einen Moment."}
        if response.status_code != 200:
            error_detail = ""
            try:
                error_detail = response.json().get("error", {}).get("message", "")
            except Exception:
                pass
            return {"error": f"Claude API-Fehler: HTTP {response.status_code}"
                             + (f" — {error_detail}" if error_detail else "")}

        data = response.json()
        raw_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                raw_text += block.get("text", "")

        return {"raw_text": raw_text}

    except requests.exceptions.Timeout:
        return {"error": "Zeitüberschreitung bei der Claude API."}
    except Exception as e:
        return {"error": f"Fehler bei der Claude-Analyse: {str(e)}"}


def _merge_batch_results(batch_results: List[Dict], document_context: str,
                         client_party: str) -> Dict:
    """Merge multiple batch issue list results into one comprehensive list."""
    all_sections = []
    total_critical = 0
    total_important = 0
    total_neutral = 0
    total_favorable = 0
    all_key_risks = []
    all_strategies = []

    section_counter = 0
    issue_counter = 0

    for parsed in batch_results:
        if not parsed or "sections" not in parsed:
            continue

        for section in parsed.get("sections", []):
            section_counter += 1
            section["number"] = _roman(section_counter)

            # Renumber issues
            for issue in section.get("issues", []):
                issue_counter += 1
                issue["ref"] = f"{section_counter}.{issue_counter}"

            all_sections.append(section)

        summary = parsed.get("executive_summary", {})
        total_critical += summary.get("critical", 0)
        total_important += summary.get("important", 0)
        total_neutral += summary.get("neutral", 0)
        total_favorable += summary.get("favorable", 0)
        all_key_risks.extend(summary.get("key_risks", []))
        strategy = summary.get("strategy", "")
        if strategy:
            all_strategies.append(strategy)

    # Deduplicate key risks
    seen_risks = set()
    unique_risks = []
    for r in all_key_risks:
        r_lower = r.lower().strip()
        if r_lower not in seen_risks:
            seen_risks.add(r_lower)
            unique_risks.append(r)

    total_issues = total_critical + total_important + total_neutral + total_favorable

    return {
        "title": f"ISSUE LIST — {document_context or 'Vertrag'}",
        "subtitle": f"Mandant: {client_party}",
        "sections": all_sections,
        "executive_summary": {
            "total_issues": total_issues,
            "critical": total_critical,
            "important": total_important,
            "neutral": total_neutral,
            "favorable": total_favorable,
            "key_risks": unique_risks[:10],
            "strategy": " ".join(all_strategies) if all_strategies else "",
        },
    }


def _roman(n: int) -> str:
    """Convert integer to Roman numeral."""
    vals = [(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),
            (50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]
    result = ''
    for val, numeral in vals:
        while n >= val:
            result += numeral
            n -= val
    return result


def analyze_changes_claude(
    changes: List[Dict],
    client_party: str,
    document_context: str = "",
    model: str = None,
    client_version: str = "a",
) -> Dict[str, Any]:
    """Send changes to Claude API for analysis, using batching for thoroughness."""
    api_key = get_api_key()
    if not api_key:
        return {
            "status": "error",
            "error": "Kein Anthropic API-Key konfiguriert. Bitte geben Sie "
                     "Ihren API-Key in den Einstellungen ein.",
        }

    use_model = model or CLAUDE_DEFAULT_MODEL

    # Split changes into batches of ~30 for thorough analysis
    BATCH_SIZE = 30
    batches = []
    for i in range(0, len(changes), BATCH_SIZE):
        batches.append(changes[i:i + BATCH_SIZE])

    if len(batches) == 0:
        return {"status": "error", "error": "Keine Änderungen zu analysieren."}

    # Process each batch
    batch_results = []
    raw_texts = []
    for batch_idx, batch in enumerate(batches):
        prompt = _build_prompt(batch, client_party, document_context,
                               client_version=client_version, provider="claude")

        # Add batch context to prompt
        if len(batches) > 1:
            batch_note = (f"\n\nHINWEIS: Dies ist Teil {batch_idx + 1} von {len(batches)} "
                          f"(Änderungen {batch_idx * BATCH_SIZE + 1} bis "
                          f"{min((batch_idx + 1) * BATCH_SIZE, len(changes))} "
                          f"von {len(changes)} gesamt). "
                          f"Erstelle für JEDE einzelne Änderung ein separates Issue.")
            prompt += batch_note

        result = _call_claude_api(api_key, use_model, prompt, max_tokens=16384)

        if "error" in result:
            return {"status": "error", "error": result["error"]}

        raw_text = result.get("raw_text", "")
        raw_texts.append(raw_text)

        parsed = _parse_json_response(raw_text)
        if parsed and "sections" in parsed:
            batch_results.append(parsed)

    if not batch_results:
        # No structured results — return raw text fallback
        return {
            "status": "ok",
            "structured": False,
            "analysis": "\n\n---\n\n".join(raw_texts),
            "model": use_model,
            "provider": "claude",
            "change_count": len(changes),
            "client_party": client_party,
        }

    # Merge all batch results into one comprehensive issue list
    merged = _merge_batch_results(batch_results, document_context, client_party)

    return {
        "status": "ok",
        "structured": True,
        "issue_list": merged,
        "raw": "\n\n---\n\n".join(raw_texts),
        "model": use_model,
        "provider": "claude",
        "change_count": len(changes),
        "client_party": client_party,
        "batches": len(batches),
    }


def analyze_changes(
    changes: List[Dict],
    client_party: str,
    document_context: str = "",
    model: str = None,
    client_version: str = "a",
    provider: str = "ollama",
) -> Dict[str, Any]:
    """Send changes to AI for analysis. Provider: 'ollama' or 'claude'."""
    if provider == "claude":
        return analyze_changes_claude(
            changes, client_party, document_context, model, client_version)

    # --- Ollama provider ---
    available, models = _check_ollama()
    if not available:
        return {
            "status": "error",
            "error": "Ollama ist nicht erreichbar. Bitte starten Sie Ollama "
                     "(https://ollama.ai) und versuchen Sie es erneut.",
        }

    use_model = model or DEFAULT_MODEL
    if use_model not in models and f"{use_model}:latest" not in models:
        available_names = [m.split(":")[0] for m in models]
        if available_names:
            use_model = models[0]
        else:
            return {
                "status": "error",
                "error": f"Kein Modell verfügbar. Bitte installieren Sie ein Modell: "
                         f"ollama pull {DEFAULT_MODEL}",
            }

    prompt = _build_prompt(changes, client_party, document_context,
                           client_version=client_version, provider="ollama")

    num_predict = min(32768, max(8192, len(changes) * 100))

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": use_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": num_predict,
                    "num_ctx": 32768,
                },
            },
            timeout=3600,
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error": f"Ollama-Fehler: HTTP {response.status_code}",
            }

        data = response.json()
        raw_text = data.get("response", "")

        return _build_result(raw_text, use_model, changes, client_party, "ollama")

    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error": "Zeitüberschreitung bei der Analyse. Versuchen Sie ein "
                     "schnelleres Modell oder weniger Änderungen.",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Fehler bei der AI-Analyse: {str(e)}",
        }
