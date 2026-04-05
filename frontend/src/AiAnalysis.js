import React, { useState, useEffect } from 'react';

const API = '/api';

const SEV = {
  KRITISCH:    { bg: 'bg-red-100',    text: 'text-red-800',    border: 'border-red-300',    dot: 'bg-red-500' },
  WICHTIG:     { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-300', dot: 'bg-orange-500' },
  NEUTRAL:     { bg: 'bg-gray-100',   text: 'text-gray-700',   border: 'border-gray-300',   dot: 'bg-gray-400' },
  VORTEILHAFT: { bg: 'bg-green-100',  text: 'text-green-800',  border: 'border-green-300',  dot: 'bg-green-500' },
};

function SeverityBadge({ severity }) {
  const s = SEV[severity?.toUpperCase()] || SEV.NEUTRAL;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold ${s.bg} ${s.text}`}>
      <span className={`w-2 h-2 rounded-full ${s.dot}`}></span>
      {severity}
    </span>
  );
}

function IssueTable({ section }) {
  return (
    <div className="mb-6">
      <div className="bg-[#1F3864] text-white px-4 py-2 rounded-t-lg">
        <h3 className="font-bold text-sm">{section.number}. {section.title}</h3>
      </div>
      {section.summary && (
        <p className="text-xs text-gray-600 italic px-4 py-2 bg-gray-50 border-x border-gray-200">
          {section.summary}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse border border-gray-300">
          <thead>
            <tr className="bg-[#1F3864] text-white">
              <th className="px-2 py-2 text-left w-16 border border-gray-500">Ref.</th>
              <th className="px-2 py-2 text-left border border-gray-500">Issue / Change</th>
              <th className="px-2 py-2 text-left w-32 border border-gray-500">Version A (Alt)</th>
              <th className="px-2 py-2 text-left w-32 border border-gray-500">Version B (Neu)</th>
              <th className="px-2 py-2 text-left w-36 border border-gray-500">Kommentar</th>
            </tr>
          </thead>
          <tbody>
            {(section.issues || []).map((issue, i) => {
              const sev = issue.severity?.toUpperCase() || 'NEUTRAL';
              const s = SEV[sev] || SEV.NEUTRAL;
              return (
                <tr key={i} className="border-b border-gray-200 hover:bg-gray-50">
                  <td className={`px-2 py-2 border border-gray-200 align-top ${s.bg}`}>
                    <div className="font-bold">{issue.ref}</div>
                    {issue.label && <div className="font-semibold text-[10px] mt-0.5">{issue.label}</div>}
                  </td>
                  <td className="px-2 py-2 border border-gray-200 align-top">
                    <SeverityBadge severity={sev} />
                    <p className="mt-1">{issue.issue}</p>
                    {issue.recommendation && (
                      <p className={`mt-1 font-bold ${s.text}`}>
                        Empfehlung: {issue.recommendation}
                      </p>
                    )}
                  </td>
                  <td className="px-2 py-2 border border-gray-200 align-top text-gray-600">
                    {issue.old_text}
                  </td>
                  <td className="px-2 py-2 border border-gray-200 align-top text-gray-600">
                    {issue.new_text}
                  </td>
                  <td className="px-2 py-2 border border-gray-200 align-top">
                    {issue.comment}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const CLAUDE_MODEL_NAMES = {
  'claude-sonnet-4-20250514': 'Claude Sonnet 4 (~6 Cent)',
  'claude-haiku-4-5-20251001': 'Claude Haiku 4.5 (~2 Cent)',
  'claude-opus-4-20250514': 'Claude Opus 4 (~30 Cent)',
};

export default function AiAnalysis({ docId, docName, versionA, versionB, onClose }) {
  const [step, setStep] = useState('form');
  const [clientParty, setClientParty] = useState('');
  const [clientVersion, setClientVersion] = useState('a');
  const [documentContext, setDocumentContext] = useState(docName || '');
  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('');
  const [ollamaModels, setOllamaModels] = useState([]);
  const [ollamaAvailable, setOllamaAvailable] = useState(null);
  const [claudeAvailable, setClaudeAvailable] = useState(false);
  const [claudeHasKey, setClaudeHasKey] = useState(false);
  const [claudeKeyPreview, setClaudeKeyPreview] = useState('');
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showApiKeyInput, setShowApiKeyInput] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (step !== 'loading') return;
    setElapsed(0);
    const iv = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(iv);
  }, [step]);

  useEffect(() => {
    fetch(`${API}/ai/status`)
      .then(r => r.json())
      .then(data => {
        setOllamaAvailable(data.available);
        setOllamaModels(data.models || []);
        if (data.models?.length > 0) setModel(data.models[0]);

        const p = data.providers || {};
        if (p.claude) {
          setClaudeAvailable(p.claude.available);
          setClaudeHasKey(p.claude.has_key);
        }
      })
      .catch(() => setOllamaAvailable(false));

    fetch(`${API}/ai/api-key`)
      .then(r => r.json())
      .then(data => {
        setClaudeHasKey(data.has_key);
        setClaudeKeyPreview(data.key_preview || '');
        if (data.has_key) setClaudeAvailable(true);
      })
      .catch(() => {});
  }, []);

  const handleSaveApiKey = async () => {
    if (!apiKeyInput.trim()) return;
    try {
      const resp = await fetch(`${API}/ai/api-key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKeyInput.trim() }),
      });
      const data = await resp.json();
      if (data.status === 'ok') {
        setClaudeHasKey(true);
        setClaudeAvailable(true);
        setClaudeKeyPreview(apiKeyInput.trim().substring(0, 10) + '...' + apiKeyInput.trim().slice(-4));
        setShowApiKeyInput(false);
        setApiKeyInput('');
      }
    } catch (e) {
      alert('Fehler: ' + e.message);
    }
  };

  const handleAnalyze = async () => {
    if (!clientParty.trim()) return;
    setStep('loading');
    setError('');
    try {
      const resp = await fetch(
        `${API}/ai/analyze/${docId}/${versionA}/${versionB}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_party: clientParty.trim(),
            client_version: clientVersion,
            document_context: documentContext.trim(),
            model: model || undefined,
            provider,
          }),
        }
      );
      const data = await resp.json();
      if (data.error) {
        setError(data.error);
        setStep('error');
      } else {
        setResult(data);
        setStep('result');
      }
    } catch (e) {
      setError('Verbindungsfehler: ' + e.message);
      setStep('error');
    }
  };

  const handleExportDocx = async () => {
    try {
      const body = result.structured
        ? { issue_list: result.issue_list, client_party: result.client_party, model: result.model, change_count: result.change_count }
        : { analysis: result.analysis || result.raw, client_party: result.client_party, model: result.model, change_count: result.change_count };
      const resp = await fetch(`${API}/ai/export-docx`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `IssueList_${result.client_party}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Fehler beim Export: ' + e.message);
    }
  };

  const issueList = result?.issue_list;
  const summary = issueList?.executive_summary;
  const canStart = clientParty.trim() && (provider === 'ollama' ? ollamaAvailable : claudeAvailable);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b bg-gradient-to-r from-[#1F3864] to-[#2D5AA0] rounded-t-2xl">
          <div className="flex items-center gap-3">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            <h2 className="text-lg font-bold text-white">AI Issue List</h2>
          </div>
          <button onClick={onClose} className="text-white/80 hover:text-white">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">

          {/* FORM */}
          {step === 'form' && (
            <div className="space-y-4">
              <p className="text-gray-600 text-sm">
                Die AI erstellt eine professionelle Issue List mit Ampelsystem, Tabellenformat und Handlungsempfehlungen.
              </p>

              {/* Provider Selection */}
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">AI-Provider</label>
                <div className="flex gap-2">
                  <button type="button" onClick={() => { setProvider('ollama'); if (ollamaModels.length > 0) setModel(ollamaModels[0]); }}
                    className={`flex-1 px-3 py-2.5 rounded-lg text-sm font-medium border-2 transition-all ${
                      provider === 'ollama'
                        ? 'bg-blue-50 border-blue-500 text-blue-800 shadow-sm'
                        : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}>
                    <div className="font-bold">Ollama (Lokal)</div>
                    <span className="block text-xs mt-0.5 opacity-70">Kostenlos, 100% lokal, ~3-5 Min</span>
                    {ollamaAvailable === false && <span className="block text-xs text-red-500 mt-0.5">Nicht erreichbar</span>}
                    {ollamaAvailable && <span className="block text-xs text-green-600 mt-0.5">Verbunden</span>}
                  </button>
                  <button type="button" onClick={() => { setProvider('claude'); setModel('claude-sonnet-4-20250514'); }}
                    className={`flex-1 px-3 py-2.5 rounded-lg text-sm font-medium border-2 transition-all ${
                      provider === 'claude'
                        ? 'bg-violet-50 border-violet-500 text-violet-800 shadow-sm'
                        : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}>
                    <div className="font-bold">Claude API</div>
                    <span className="block text-xs mt-0.5 opacity-70">Schneller, besser, ~2-30 Cent</span>
                    {claudeHasKey
                      ? <span className="block text-xs text-green-600 mt-0.5">API-Key konfiguriert</span>
                      : <span className="block text-xs text-orange-500 mt-0.5">API-Key erforderlich</span>
                    }
                  </button>
                </div>
              </div>

              {/* Claude API Key Section */}
              {provider === 'claude' && (
                <div className="bg-violet-50 border border-violet-200 rounded-lg p-3">
                  {claudeHasKey && !showApiKeyInput ? (
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-xs font-semibold text-violet-800">API-Key: </span>
                        <code className="text-xs text-violet-600 bg-violet-100 px-1.5 py-0.5 rounded">{claudeKeyPreview}</code>
                      </div>
                      <button onClick={() => setShowApiKeyInput(true)}
                        className="text-xs text-violet-600 hover:text-violet-800 underline">
                        Ändern
                      </button>
                    </div>
                  ) : (
                    <div>
                      <label className="block text-xs font-semibold text-violet-800 mb-1">
                        Anthropic API-Key
                      </label>
                      <div className="flex gap-2">
                        <input type="password" value={apiKeyInput}
                          onChange={e => setApiKeyInput(e.target.value)}
                          placeholder="sk-ant-api03-..."
                          className="flex-1 border border-violet-300 rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-violet-500 font-mono"
                          onKeyDown={e => e.key === 'Enter' && handleSaveApiKey()}
                        />
                        <button onClick={handleSaveApiKey}
                          className="px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded text-sm font-medium">
                          Speichern
                        </button>
                        {claudeHasKey && (
                          <button onClick={() => setShowApiKeyInput(false)}
                            className="px-2 py-1.5 text-violet-600 hover:text-violet-800 text-sm">
                            Abbrechen
                          </button>
                        )}
                      </div>
                      <p className="text-[10px] text-violet-500 mt-1">
                        Key von console.anthropic.com — wird lokal gespeichert
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Ollama warning */}
              {provider === 'ollama' && ollamaAvailable === false && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="text-red-800 font-semibold text-sm">Ollama nicht erreichbar</p>
                  <p className="text-red-600 text-xs mt-1">
                    Bitte starten Sie Ollama und laden Sie ein Modell:
                    <code className="bg-red-100 px-1 rounded ml-1">ollama pull qwen2.5:14b</code>
                  </p>
                </div>
              )}

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">Wen vertreten Sie? *</label>
                <input type="text" value={clientParty} onChange={e => setClientParty(e.target.value)}
                  placeholder="z.B. Käufer, Verkäufer GmbH, Mieter, Lizenzgeber..."
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" autoFocus />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">Welche Version ist Ihre? *</label>
                <div className="flex gap-2">
                  {['a', 'b'].map(v => (
                    <button key={v} type="button" onClick={() => setClientVersion(v)}
                      className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                        clientVersion === v ? 'bg-blue-100 border-blue-500 text-blue-800' : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
                      }`}>
                      Version {v.toUpperCase()} (V{v === 'a' ? versionA : versionB})
                      <span className="block text-xs mt-0.5 opacity-70">{v === 'a' ? 'Vorversion — Standard' : 'Aktuelle Version'}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">Dokumenttyp (optional)</label>
                <input type="text" value={documentContext} onChange={e => setDocumentContext(e.target.value)}
                  placeholder="z.B. SPA, Kaufvertrag, Mietvertrag, NDA..."
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500" />
              </div>

              {/* Model Selection */}
              {provider === 'ollama' && ollamaModels.length > 0 && (
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1">Ollama-Modell</label>
                  <select value={model} onChange={e => setModel(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500">
                    {ollamaModels.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
              )}

              {provider === 'claude' && (
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1">Claude-Modell</label>
                  <select value={model} onChange={e => setModel(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500">
                    {Object.entries(CLAUDE_MODEL_NAMES).map(([id, name]) => (
                      <option key={id} value={id}>{name}</option>
                    ))}
                  </select>
                </div>
              )}

              <button onClick={handleAnalyze} disabled={!canStart}
                className={`w-full font-semibold py-2.5 rounded-lg transition-colors text-white ${
                  provider === 'claude'
                    ? 'bg-violet-600 hover:bg-violet-700 disabled:bg-gray-300'
                    : 'bg-[#1F3864] hover:bg-[#2D5AA0] disabled:bg-gray-300'
                }`}>
                {provider === 'claude' ? 'Issue List generieren (Claude API)' : 'Issue List generieren (Ollama)'}
              </button>
            </div>
          )}

          {/* LOADING */}
          {step === 'loading' && (() => {
            const isClaude = provider === 'claude';
            const maxTime = isClaude ? 30 : 180;
            const pct = Math.min(95, Math.round((elapsed / maxTime) * 100));
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            const phases = isClaude
              ? [[0,'Änderungen werden aufbereitet...'],[5,'Anfrage an Claude API...'],[15,'AI analysiert die Klauseln...'],[50,'Issue List wird erstellt...'],[80,'Antwort wird verarbeitet...']]
              : [[0,'Änderungen werden aufbereitet...'],[10,'Prompt wird an LLM gesendet...'],[20,'AI analysiert die Klauseln...'],[40,'Risikobewertung läuft...'],[60,'Issue List wird strukturiert...'],[80,'Tabellen werden erstellt...'],[90,'Analyse wird abgeschlossen...']];
            const phase = [...phases].reverse().find(([p]) => pct >= p)?.[1] || phases[0][1];
            return (
              <div className="py-8 space-y-6">
                <div className="text-center">
                  <div className={`inline-block w-10 h-10 border-4 ${isClaude ? 'border-violet-200 border-t-violet-600' : 'border-blue-200 border-t-[#1F3864]'} rounded-full animate-spin mb-3`}></div>
                  <p className="text-gray-700 font-semibold">{phase}</p>
                  <p className="text-gray-400 text-sm mt-1">{mins > 0 ? `${mins}:${secs.toString().padStart(2,'0')}` : `${secs}s`} vergangen</p>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                  <div className={`h-full rounded-full transition-all duration-1000 ${isClaude ? 'bg-gradient-to-r from-violet-500 to-violet-600' : 'bg-gradient-to-r from-[#1F3864] to-[#2D5AA0]'}`} style={{width:`${pct}%`}}></div>
                </div>
                <p className="text-center text-xs text-gray-400">
                  {isClaude
                    ? `Geschätzt ca. 10-20 Sekunden mit ${CLAUDE_MODEL_NAMES[model] || model}`
                    : `Geschätzt ca. 2-3 Minuten mit ${model || 'qwen2.5:14b'}`
                  }
                </p>
              </div>
            );
          })()}

          {/* ERROR */}
          {step === 'error' && (
            <div className="space-y-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-4"><p className="text-red-800">{error}</p></div>
              <button onClick={() => setStep('form')} className="text-blue-600 hover:text-blue-800 text-sm font-medium">&larr; Zurück</button>
            </div>
          )}

          {/* RESULT — Structured */}
          {step === 'result' && result && result.structured && issueList && (
            <div className="space-y-4">
              {/* Title bar */}
              <div className="bg-[#1F3864] text-white px-4 py-3 rounded-lg">
                <h2 className="font-bold text-base">{issueList.title}</h2>
                <p className="text-xs text-blue-200 mt-1">
                  {issueList.subtitle} |{' '}
                  <span className={result.provider === 'claude' ? 'text-violet-300' : ''}>
                    {result.provider === 'claude' ? `Claude (${CLAUDE_MODEL_NAMES[result.model] || result.model})` : result.model}
                  </span>
                  {' '}| {result.change_count} Änderungen
                </p>
              </div>

              {/* Summary stats */}
              {summary && (
                <div className="grid grid-cols-4 gap-2">
                  {[['critical','Kritisch','bg-red-100 text-red-800 border-red-200'],
                    ['important','Wichtig','bg-orange-100 text-orange-800 border-orange-200'],
                    ['neutral','Neutral','bg-gray-100 text-gray-700 border-gray-200'],
                    ['favorable','Vorteilhaft','bg-green-100 text-green-800 border-green-200']
                  ].map(([k, label, cls]) => (
                    <div key={k} className={`text-center px-3 py-2 rounded-lg border ${cls}`}>
                      <div className="text-2xl font-bold">{summary[k] || 0}</div>
                      <div className="text-xs font-medium">{label}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Strategy */}
              {summary?.strategy && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                  <p className="text-xs font-semibold text-blue-800 mb-1">Verhandlungsstrategie</p>
                  <p className="text-sm text-blue-900">{summary.strategy}</p>
                </div>
              )}

              {/* Key risks */}
              {summary?.key_risks?.length > 0 && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="text-xs font-semibold text-red-800 mb-1">Kritische Punkte</p>
                  <ul className="text-sm text-red-900 list-disc list-inside">
                    {summary.key_risks.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}

              {/* Issue tables per section */}
              {(issueList.sections || []).map((sec, i) => (
                <IssueTable key={i} section={sec} />
              ))}

              {/* Actions */}
              <div className="flex gap-2 pt-2 border-t">
                <button onClick={handleExportDocx}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Als Word speichern
                </button>
                <button onClick={() => { setStep('form'); setResult(null); }}
                  className="px-4 py-2 border border-gray-300 hover:bg-gray-50 rounded-lg text-sm font-medium text-gray-700">
                  Neue Analyse
                </button>
              </div>
            </div>
          )}

          {/* RESULT — Fallback (unstructured) */}
          {step === 'result' && result && !result.structured && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full text-xs font-medium">{result.model}</span>
                <span>{result.change_count} Änderungen</span>
                <span>| Mandant: {result.client_party}</span>
              </div>
              <div className="bg-gray-50 border rounded-lg p-4">
                <pre className="whitespace-pre-wrap text-sm text-gray-800 font-sans leading-relaxed">{result.analysis || result.raw}</pre>
              </div>
              <div className="flex gap-2">
                <button onClick={handleExportDocx}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold">
                  Als Word speichern
                </button>
                <button onClick={() => { setStep('form'); setResult(null); }}
                  className="px-4 py-2 border border-gray-300 hover:bg-gray-50 rounded-lg text-sm font-medium text-gray-700">
                  Neue Analyse
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
