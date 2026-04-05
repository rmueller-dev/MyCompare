"""
AI-powered document change analysis using local Ollama LLM.
Generates an issue list from redline changes, evaluating each change
from the perspective of the user's client (party representation).
"""
import json
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
    """Build the analysis prompt for the LLM.

    Args:
        client_version: 'a' means client authored Version A (old), counterparty
                        made changes in Version B (new).
                        'b' means client authored Version B (new), the old
                        version is the counterparty's.
    """
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
        elif "Tabelle" in ch_type:
            changes_text.append(f"{i}. TABELLENÄNDERUNG: \"{old}\" → \"{new}\"")
        elif "Formatierung" in ch_type:
            changes_text.append(f"{i}. FORMATIERUNG (Absatz {para}): {old or new}")
        else:
            changes_text.append(f"{i}. {ch_type} (Absatz {para}): \"{old}\" → \"{new}\"")

    changes_block = "\n".join(changes_text)

    if client_version == "a":
        perspective = (
            f"Version A (alt) ist das Dokument deines Mandanten ({client_party}). "
            f"Version B (neu) enthält die Änderungen der Gegenseite. "
            f"Analysiere was die Gegenseite geändert hat und bewerte die Auswirkungen "
            f"auf deinen Mandanten."
        )
    else:
        perspective = (
            f"Version B (neu) ist das Dokument deines Mandanten ({client_party}). "
            f"Version A (alt) ist das Dokument der Gegenseite. "
            f"Die Änderungen zeigen die Unterschiede zwischen dem Entwurf der Gegenseite "
            f"und dem Entwurf deines Mandanten. Bewerte was dein Mandant geändert hat "
            f"und welche Positionen der Gegenseite dadurch adressiert werden."
        )

    prompt = f"""Du bist ein erfahrener deutscher Wirtschaftsanwalt. Du vertrittst: **{client_party}**

{perspective}

{f"Dokumentkontext: {document_context}" if document_context else ""}

ÄNDERUNGEN (Version A → Version B):
{changes_block}

Erstelle eine strukturierte Issue List im folgenden Format. Bewerte jede Änderung aus Sicht deines Mandanten ({client_party}):

Für jede relevante Änderung:
1. **Änderung Nr. [X]**: Kurze Beschreibung der Änderung
   - **Bewertung**: [KRITISCH / WICHTIG / NEUTRAL / VORTEILHAFT]
   - **Risiko für {client_party}**: Beschreibe das konkrete Risiko oder den Vorteil
   - **Empfehlung**: Was sollte der Mandant tun? (Akzeptieren / Ablehnen / Nachverhandeln / Gegenvorschlag)
   - **Begründung**: Juristische Begründung in 1-2 Sätzen

Am Ende:
- **Zusammenfassung**: Gesamtbewertung der Änderungen (1-3 Sätze)
- **Kritische Punkte**: Liste der Änderungen die sofort adressiert werden müssen
- **Verhandlungsstrategie**: Kurzer Vorschlag zum weiteren Vorgehen

Antworte auf Deutsch. Sei präzise und praxisorientiert."""

    return prompt


def analyze_changes(
    changes: List[Dict],
    client_party: str,
    document_context: str = "",
    model: str = None,
    client_version: str = "a",
) -> Dict[str, Any]:
    """
    Send changes to Ollama for AI analysis.

    Args:
        changes: List of change dicts from the redline (type, old, new, para)
        client_party: Who the user represents (e.g. "Käufer", "Verkäufer GmbH")
        document_context: Optional context about the document type
        model: Ollama model name (default: llama3.1)

    Returns:
        Dict with 'analysis' text, 'model' used, 'status'
    """
    available, models = _check_ollama()
    if not available:
        return {
            "status": "error",
            "error": "Ollama ist nicht erreichbar. Bitte starten Sie Ollama "
                     "(https://ollama.ai) und versuchen Sie es erneut.",
            "analysis": None,
        }

    use_model = model or DEFAULT_MODEL
    # Check if requested model is available
    if use_model not in models and f"{use_model}:latest" not in models:
        # Try to find a similar model
        available_names = [m.split(":")[0] for m in models]
        if available_names:
            use_model = models[0]  # Use first available model
        else:
            return {
                "status": "error",
                "error": f"Kein Modell verfügbar. Bitte installieren Sie ein Modell: "
                         f"ollama pull {DEFAULT_MODEL}",
                "analysis": None,
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
                    "temperature": 0.3,
                    "num_predict": 4096,
                },
            },
            timeout=3600,  # 60 min timeout for large analyses
        )

        if response.status_code != 200:
            return {
                "status": "error",
                "error": f"Ollama-Fehler: HTTP {response.status_code}",
                "analysis": None,
            }

        data = response.json()
        analysis_text = data.get("response", "")

        return {
            "status": "ok",
            "analysis": analysis_text,
            "model": use_model,
            "change_count": len(changes),
            "client_party": client_party,
        }

    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error": "Zeitüberschreitung bei der Analyse. Das Dokument ist "
                     "möglicherweise zu groß. Versuchen Sie ein schnelleres Modell.",
            "analysis": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Fehler bei der AI-Analyse: {str(e)}",
            "analysis": None,
        }
