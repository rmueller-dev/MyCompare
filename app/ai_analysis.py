"""
AI-powered document change analysis using local Ollama LLM.
Generates a professional Issue List from redline changes, structured
in sections with traffic-light severity ratings, like M&A transaction issue lists.
"""
import json
import re
import requests
from typing import List, Dict, Any

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:14b"


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


def _build_prompt(changes: List[Dict], client_party: str,
                  document_context: str = "", client_version: str = "a") -> str:
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
        col_a_label = f"Entwurf {client_party}"
        col_b_label = "Mark-up Gegenseite"
    else:
        perspective = (
            f"Version B (neu) ist das Dokument deines Mandanten ({client_party}). "
            f"Version A (alt) ist das Dokument der Gegenseite."
        )
        col_a_label = "Entwurf Gegenseite"
        col_b_label = f"Mark-up {client_party}"

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
- Gruppiere verwandte Änderungen in Abschnitte
- Bewerte aus Sicht von {client_party}
- Sei präzise und praxisorientiert
- Antworte auf Deutsch
- NUR valides JSON, keine Erklärungen davor oder danach"""

    return prompt


def _parse_json_response(text: str) -> Dict:
    """Try to extract JSON from LLM response, handling common issues."""
    # Try direct parse
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


def analyze_changes(
    changes: List[Dict],
    client_party: str,
    document_context: str = "",
    model: str = None,
    client_version: str = "a",
) -> Dict[str, Any]:
    """Send changes to Ollama for AI analysis, returns structured issue list."""
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
                           client_version=client_version)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": use_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 8192,
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

        # Try to parse structured JSON
        parsed = _parse_json_response(raw_text)

        if parsed and "sections" in parsed:
            return {
                "status": "ok",
                "structured": True,
                "issue_list": parsed,
                "raw": raw_text,
                "model": use_model,
                "change_count": len(changes),
                "client_party": client_party,
            }
        else:
            # Fallback: return raw text
            return {
                "status": "ok",
                "structured": False,
                "analysis": raw_text,
                "model": use_model,
                "change_count": len(changes),
                "client_party": client_party,
            }

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
