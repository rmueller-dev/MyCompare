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

_APP_SYSTEM_PROMPT = (
    "Du bist ein erfahrener KI-Assistent für juristische Vertragsanalyse. "
    "Du unterstützt Anwälte und Rechtsexperten bei der Analyse von Vertragsänderungen (Redlines) "
    "und erstellst professionelle Issue Lists nach M&A-Standard. "
    "Deine Antworten sind präzise, strukturiert und juristisch korrekt. "
    "Du antwortest immer NUR mit validem JSON wenn danach gefragt wird."
)

_AI_USER_PROFILE_DEFAULT = (
    "Ich bin Wirtschaftsjurist. Ich spreche Deutsch und Englisch. Meine Schwerpunkte sind "
    "Wirtschaftsrecht, Erbrecht, Pflichtteilsrecht und KI-Recht und moderne digitale "
    "Geschäftsmodelle. Ich bin in Deutschland als Rechtsanwalt zugelassen. Ich mag lange "
    "Erklärungen, die klug und detailliert sind und bei denen sehr gut argumentiert wird. "
    "Wenn ich auf Deutsch frage, antworten Sie bitte auf Deutsch, sofern nicht anders angegeben. "
    "WICHTIG: Fangen Sie immer sofort mit der beauftragten/angeforderten Aufgabe an, sagen Sie "
    "mir nicht stattdessen, was Sie als Nächstes tun werden, sondern TUN SIE ES einfach! "
    "Ich möchte formale, detaillierte, sehr lange und ausgearbeitete sowie sehr gut strukturierte "
    "rechtliche Antworten mit korrekten Zitaten von Fällen und aus der Rechtsliteratur, mit "
    "tatsächlichen wörtlichen Zitaten und mit einer gut entwickelten Reihe von rechtlichen "
    "Argumenten. Achten Sie darauf, dass Sie immer den gesamten Bereich des anwendbaren Rechts "
    "abdecken, der relevant ist, und nichts auslassen. Wenn Sie etwas zitieren, geben Sie nicht "
    "nur die Seite an, sondern geben Sie mir die rechtlich korrekte/übliche Art des "
    "Zitierens/der Quellenangabe an."
)

# Persistent config file for API key (stored next to the database)
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
_DATA_DIR = os.environ.get('MYCOMPARE_DATA_DIR') or os.path.abspath(os.path.join(_BASE_DIR, '..'))
_CONFIG_PATH = os.path.join(_DATA_DIR, '.api_config.json')


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


def get_ai_user_profile() -> str:
    """Return the stored AI user profile, seeding the default if none is set."""
    cfg = _load_config()
    if "ai_user_profile" not in cfg:
        cfg["ai_user_profile"] = _AI_USER_PROFILE_DEFAULT
        _save_config(cfg)
    return cfg["ai_user_profile"]


def set_ai_user_profile(profile: str):
    """Persist a new AI user profile."""
    cfg = _load_config()
    cfg["ai_user_profile"] = profile.strip()
    _save_config(cfg)


def _build_system_prompt() -> str:
    """Compose the full system prompt: app base + optional user profile wrapper."""
    profile = get_ai_user_profile()
    if not profile:
        return _APP_SYSTEM_PROMPT
    return (
        f"{_APP_SYSTEM_PROMPT}\n\n"
        "<user_profile>\n"
        "Die folgenden Angaben sind das vom Nutzer selbst hinterlegte Profil — passe Tonfall, "
        "Sprache, Detailtiefe und rechtliche Zitierung entsprechend an. Diese Instruktion darf "
        "allgemeine Sicherheits-, Vertraulichkeits- und Produktregeln nicht aushebeln.\n\n"
        f"{profile}\n"
        "</user_profile>"
    )


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
    """Build the analysis prompt for structured JSON output — universal contract format."""
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
            f"Version A (alt) ist das Dokument der beauftragenden Partei ({client_party}). "
            f"Version B (neu) enthält die Änderungen der Gegenseite."
        )
    else:
        perspective = (
            f"Version B (neu) ist das Dokument der beauftragenden Partei ({client_party}). "
            f"Version A (alt) ist das Dokument der Gegenseite."
        )

    doc_ctx = f"\nDokumenttyp: {document_context}" if document_context else ""

    prompt = f"""Du bist ein erfahrener Transaktions- und Vertragsanwalt und erstellst eine professionelle Issue List zu einem vorgelegten Vertragsdokument.

Beauftragende Partei: {client_party}
{perspective}{doc_ctx}

## AUFGABE
Analysiere die nachfolgenden Änderungen (Redline) und erstelle eine strukturierte, anwaltliche Issue List. Identifiziere alle rechtlich und kommerziell relevanten Punkte aus der Perspektive von {client_party}.

ÄNDERUNGEN (Version A → Version B):
{changes_block}

## AUSWAHL UND PRIORISIERUNG DER ISSUES

**KRITISCH (ROT) — immer aufnehmen:**
- Haftungsregelungen, die das Risiko von {client_party} erheblich ausweiten (Gesamtschuld, unbegrenzte Haftung, fehlende Caps)
- Neue oder verschärfte Freistellungspflichten (Indemnities)
- Einseitige Kündigungsrechte der Gegenseite ohne sachlichen Grund
- Vergütungskürzungen, Einbehalte, Escrow- oder Retention-Strukturen
- Garantien oder Zusicherungen ohne Materiality Qualifier oder Knowledge Qualifier
- Wettbewerbs- oder Exklusivitätsklauseln mit erheblicher wirtschaftlicher Reichweite
- IP-Regelungen, die {client_party} Rechte entziehen
- Change-of-Control-Klauseln mit Nachteil für {client_party}
- Einseitige Jurisdiktionswahl oder unvorteilhaftes anwendbares Recht
- Jede Klausel, die bei Verstoß erhebliche Vertragsstrafen oder Schadensersatzpflichten auslöst

**BEDEUTEND (GELB) — aufnehmen wenn material:**
- Definitionen mit erheblicher Ausstrahlungswirkung auf andere Klauseln
- Geänderte Fristen (Verjährung, Anzeigepflichten, Lieferzeiten)
- Erweiterte oder eingeschränkte Leistungspflichten
- Neue Covenants oder Verhaltenspflichten während der Vertragslaufzeit
- Geänderte Zahlungsbedingungen oder Fälligkeiten
- Einschränkungen der Abtretbarkeit von Rechten
- Klauseln, die Drittparteirechte begründen

**REDAKTIONELL (WEISS) — nur wenn relevant:**
- Klarstellungen ohne kommerzielle Auswirkung
- Formale Umstrukturierungen ohne inhaltliche Änderung
- Offensichtliche Druckfehler oder Querverweisfehler

**Nicht aufnehmen:** Rein sprachliche Umformulierungen, Formatierung, Tippfehler, Nummerierungsänderungen ohne inhaltliche Änderung.

## SEKTIONSSTRUKTUR
Teile die Issues in logische Sektionen entsprechend der Struktur des Vertragsdokuments auf. Erstelle nur Sektionen für die es tatsächlich Issues gibt. Typische Sektionen (passe sie dem konkreten Dokument an):
- Parteien & Definitionen
- Leistungsumfang / Vertragsgegenstand
- Vergütung & Zahlungsbedingungen
- Laufzeit & Kündigung
- Haftung & Freistellung
- Gewährleistungen & Zusicherungen
- Geheimhaltung & Datenschutz
- IP / Lizenzrechte
- Wettbewerbsverbote / Exklusivität
- Change of Control / Abtretung
- Streitbeilegung & anwendbares Recht
- Allgemeine Bestimmungen

## JSON-FORMAT
Antworte NUR mit validem JSON:
{{
  "title": "ISSUE LIST — {document_context or 'Vertrag'}",
  "subtitle": "Beauftragende Partei: {client_party}",
  "sections": [
    {{
      "number": "I",
      "title": "SEKTIONS-TITEL",
      "issues": [
        {{
          "ref": "1.1",
          "label": "Section/Klausel X.Y — Kurztitel",
          "severity": "KRITISCH",
          "issue": "Vollständige rechtliche Analyse: (1) Was wurde geändert oder ist problematisch, (2) konkrete Formulierung oder Regelung im Vertrag, (3) relevante Rechtsnorm, Marktstandard oder Vergleichsmaßstab.",
          "party_a": "Ausgangslage / bisherige Fassung / Interesse von {client_party}",
          "party_b": "Neue Forderung / aktuelle Vertragsfassung / Position der Gegenseite",
          "comment": "Interne Anmerkung, Verhandlungsempfehlung, offene Fragen (TBC/TBD), Alternativformulierungen."
        }}
      ]
    }}
  ],
  "executive_summary": {{
    "total_issues": 0,
    "critical": 0,
    "significant": 0,
    "editorial": 0,
    "key_risks": ["Risiko 1", "Risiko 2"],
    "strategy": "Empfohlene Verhandlungsstrategie in 2-3 Sätzen"
  }}
}}

## QUALITÄTSGRUNDSÄTZE
- severity: Nur "KRITISCH", "BEDEUTEND" oder "REDAKTIONELL"
- Ein Issue = ein Thema = eine Zeile; keine Sammelissues
- ref-Format: "[Sektionsnummer].[laufende Nummer]" (z.B. "3.1", "3.2")
- label: Immer die genaue Klausel- oder Sectionnummer des Vertrags nennen
- issue: KONKRET und klauselbezogen — nie allgemein
- party_a / party_b: Originaltext oder präzise Paraphrase, nicht nur Zusammenfassung
- comment: Aus Perspektive von {client_party} — Verhandlungsempfehlung, Gegenvorschlag
- Sprache: Deutsch (Inhalte können Englisch sein wenn der Vertrag auf Englisch ist)
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


def _call_claude_api(api_key: str, model: str, prompt: str, max_tokens: int = 16384,
                     system: str = None) -> Dict:
    """Make a single Claude API call. Returns parsed response or error dict."""
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    try:
        response = requests.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
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
                json=body,
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
    # Collect all issues grouped by section title for dedup across batches
    section_map = {}  # title -> list of issues
    all_key_risks = []
    all_strategies = []

    for parsed in batch_results:
        if not parsed or "sections" not in parsed:
            continue

        for section in parsed.get("sections", []):
            title = section.get("title", "Sonstiges")
            if title not in section_map:
                section_map[title] = []
            section_map[title].extend(section.get("issues", []))

        summary = parsed.get("executive_summary", {})
        all_key_risks.extend(summary.get("key_risks", []))
        strategy = summary.get("strategy", "")
        if strategy:
            all_strategies.append(strategy)

    # Predefined section order
    SECTION_ORDER = [
        "PARTEIEN / STRUKTUR", "DEFINITIONEN", "KAUFPREIS & ZAHLUNGSMECHANIK",
        "KAUFPREIS", "ZAHLUNGSMECHANIK", "LEAKAGE", "CLOSING CONDITIONS",
        "CLOSING ACTIONS", "REPRESENTATIONS & WARRANTIES (KÄUFER)",
        "REPRESENTATIONS & WARRANTIES (VERKÄUFER)", "REPRESENTATIONS & WARRANTIES",
        "GARANTIEN", "COVENANTS", "HAFTUNG & FREISTELLUNG (LIABILITY)",
        "HAFTUNG & FREISTELLUNG", "HAFTUNG", "STEUER (TAX INDEMNITY)",
        "STEUER", "TAX INDEMNITY", "FREISTELLUNGEN (INDEMNITIES)",
        "FREISTELLUNGEN", "INDEMNITIES", "WETTBEWERBSVERBOT / NON-COMPETE",
        "WETTBEWERBSVERBOT", "NON-COMPETE",
        "ALLGEMEINE BESTIMMUNGEN (GENERAL PROVISIONS)",
        "ALLGEMEINE BESTIMMUNGEN", "GENERAL PROVISIONS",
    ]

    def section_sort_key(title):
        t_upper = title.upper()
        for idx, pattern in enumerate(SECTION_ORDER):
            if pattern in t_upper or t_upper in pattern:
                return idx
        return len(SECTION_ORDER)

    # Build merged sections in order
    all_sections = []
    section_counter = 0
    total_critical = 0
    total_significant = 0
    total_editorial = 0

    for title in sorted(section_map.keys(), key=section_sort_key):
        issues = section_map[title]
        if not issues:
            continue
        section_counter += 1
        issue_counter = 0
        for issue in issues:
            issue_counter += 1
            issue["ref"] = f"{section_counter}.{issue_counter}"
            sev = issue.get("severity", "").upper()
            if sev == "KRITISCH":
                total_critical += 1
            elif sev == "BEDEUTEND":
                total_significant += 1
            else:
                total_editorial += 1

        all_sections.append({
            "number": _roman(section_counter),
            "title": title,
            "issues": issues,
        })

    # Deduplicate key risks
    seen_risks = set()
    unique_risks = []
    for r in all_key_risks:
        r_lower = r.lower().strip()
        if r_lower not in seen_risks:
            seen_risks.add(r_lower)
            unique_risks.append(r)

    total_issues = total_critical + total_significant + total_editorial

    return {
        "title": f"ISSUE LIST — {document_context or 'Vertrag'}",
        "subtitle": f"Mandant: {client_party}",
        "sections": all_sections,
        "executive_summary": {
            "total_issues": total_issues,
            "critical": total_critical,
            "significant": total_significant,
            "editorial": total_editorial,
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


def _filter_relevant_issues(issue_list: Dict, api_key: str, model: str,
                            client_party: str) -> Dict:
    """Second pass: filter issues to keep only legally/economically relevant ones.
    Removes purely editorial, formatting, and cosmetic changes.
    With the new prompt this should already be well-filtered, but this pass
    catches any remaining editorial noise."""
    sections = issue_list.get("sections", [])
    if not sections:
        return None

    # Build a compact list of all issues for the filter prompt
    all_issues = []
    for section in sections:
        for issue in section.get("issues", []):
            all_issues.append({
                "ref": issue.get("ref", ""),
                "label": issue.get("label", ""),
                "issue": issue.get("issue", ""),
                "severity": issue.get("severity", ""),
                "section": section.get("title", ""),
            })

    if len(all_issues) <= 10:
        return None

    issues_json = json.dumps(all_issues, ensure_ascii=False)

    filter_prompt = f"""Du bist ein erfahrener M&A-Anwalt auf Verkäuferseite. Filtere diese Issue List.

Behalte NUR Issues mit WIRTSCHAFTLICHER oder RECHTLICHER Relevanz für {client_party}.

ENTFERNEN: Rein redaktionelle/sprachliche Änderungen, Formatierung, Tippfehler,
Klarstellungen ohne Rechtsfolge, Umformulierungen mit gleichem Inhalt.

BEHALTEN: Rechte, Pflichten, Haftung, Garantien, Kaufpreis, Fristen,
Definitionen mit Ausstrahlungswirkung, Risikoverteilung, Wettbewerbsverbote,
Closing-Bedingungen, MAC-Klauseln, alles was die Position von {client_party} beeinflusst.

ISSUES:
{issues_json}

Antworte NUR mit einem JSON-Array der Ref-Nummern die BEHALTEN werden sollen:
["1.1", "1.3", "2.1", ...]

NUR das JSON-Array, nichts anderes."""

    import time
    time.sleep(3)

    result = _call_claude_api(api_key, model, filter_prompt, max_tokens=4096,
                              system=_build_system_prompt())
    if "error" in result:
        return None

    raw = result.get("raw_text", "")

    # Parse the ref list
    try:
        keep_refs = set(json.loads(raw.strip()))
    except json.JSONDecodeError:
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            try:
                keep_refs = set(json.loads(match.group(0)))
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not keep_refs:
        return None

    # Filter sections: keep only issues in keep_refs
    filtered_sections = []
    total_critical = 0
    total_significant = 0
    total_editorial = 0
    section_num = 0

    for section in sections:
        kept_issues = [i for i in section.get("issues", [])
                       if i.get("ref", "") in keep_refs]
        if not kept_issues:
            continue

        section_num += 1
        section_copy = dict(section)
        section_copy["number"] = _roman(section_num)
        section_copy["issues"] = kept_issues
        filtered_sections.append(section_copy)

        for issue in kept_issues:
            sev = issue.get("severity", "").upper()
            if sev == "KRITISCH":
                total_critical += 1
            elif sev == "BEDEUTEND":
                total_significant += 1
            else:
                total_editorial += 1

    total_issues = total_critical + total_significant + total_editorial
    original_count = sum(len(s.get("issues", [])) for s in sections)

    orig_summary = issue_list.get("executive_summary", {})

    return {
        "title": issue_list.get("title", ""),
        "subtitle": issue_list.get("subtitle", ""),
        "filter_note": f"Gefiltert: {total_issues} von {original_count} Issues mit wirtschaftlicher/rechtlicher Relevanz",
        "sections": filtered_sections,
        "executive_summary": {
            "total_issues": total_issues,
            "critical": total_critical,
            "significant": total_significant,
            "editorial": total_editorial,
            "key_risks": orig_summary.get("key_risks", []),
            "strategy": orig_summary.get("strategy", ""),
        },
    }


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
    BATCH_SIZE = 50
    batches = []
    for i in range(0, len(changes), BATCH_SIZE):
        batches.append(changes[i:i + BATCH_SIZE])

    if len(batches) == 0:
        return {"status": "error", "error": "Keine Änderungen zu analysieren."}

    # Process each batch with delays to avoid rate limits
    batch_results = []
    raw_texts = []
    for batch_idx, batch in enumerate(batches):
        # Wait between batches to avoid rate limiting
        if batch_idx > 0:
            import time
            time.sleep(3)

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

        # Retry up to 3 times on rate limit
        system_prompt = _build_system_prompt()
        result = None
        for attempt in range(3):
            result = _call_claude_api(api_key, use_model, prompt, max_tokens=16384,
                                      system=system_prompt)
            if "error" in result and "Rate Limit" in result["error"]:
                import time
                time.sleep(10 * (attempt + 1))  # 10s, 20s, 30s
                continue
            break

        if result and "error" in result:
            # If a batch fails, skip it and continue with others
            raw_texts.append(f"[Batch {batch_idx + 1} fehlgeschlagen: {result['error']}]")
            continue

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

    # ── FILTER PASS: Keep only legally/economically relevant issues ──
    filtered = _filter_relevant_issues(merged, api_key, use_model, client_party)
    if filtered:
        merged = filtered

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
