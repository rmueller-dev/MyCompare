import React, { useState, useEffect, useRef } from 'react';

const API = '/api';

const SEV = {
  KRITISCH:     { bg: 'bg-red-50',    text: 'text-red-800',    border: 'border-red-300',    dot: 'bg-red-500',    rowBg: '#FDEDEC' },
  BEDEUTEND:    { bg: 'bg-yellow-50',  text: 'text-yellow-800', border: 'border-yellow-300', dot: 'bg-yellow-500', rowBg: '#FEF9E7' },
  REDAKTIONELL: { bg: 'bg-white',      text: 'text-gray-600',   border: 'border-gray-300',   dot: 'bg-gray-400',   rowBg: '#FFFFFF' },
};

function SeverityBadge({ severity }) {
  const s = SEV[severity?.toUpperCase()] || SEV.REDAKTIONELL;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold ${s.bg} ${s.text}`}>
      <span className={`w-2 h-2 rounded-full ${s.dot}`}></span>
      {severity}
    </span>
  );
}

function IssueTable({ section, clientParty }) {
  return (
    <div className="mb-6">
      <div className="bg-[#2E5FA3] text-white px-4 py-2 rounded-t-lg">
        <h3 className="font-bold text-sm">{section.number}. {section.title}</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse border border-gray-300">
          <thead>
            <tr className="bg-[#1F3864] text-white">
              <th className="px-2 py-2 text-left w-10 border border-gray-500">Nr.</th>
              <th className="px-2 py-2 text-left w-24 border border-gray-500">Ref.</th>
              <th className="px-2 py-2 text-left border border-gray-500" style={{minWidth:'200px'}}>Issue / Änderung</th>
              <th className="px-2 py-2 text-left w-36 border border-gray-500">Position {clientParty || 'Partei A'}</th>
              <th className="px-2 py-2 text-left w-36 border border-gray-500">Position Gegenseite</th>
              <th className="px-2 py-2 text-left w-44 border border-gray-500">Kommentare / Empfehlung</th>
            </tr>
          </thead>
          <tbody>
            {(section.issues || []).map((issue, i) => {
              const sev = issue.severity?.toUpperCase() || 'REDAKTIONELL';
              const s = SEV[sev] || SEV.REDAKTIONELL;
              return (
                <tr key={i} className="border-b border-gray-200" style={{backgroundColor: s.rowBg}}>
                  <td className="px-2 py-2 border border-gray-200 align-top font-bold text-center">
                    {i + 1}
                  </td>
                  <td className="px-2 py-2 border border-gray-200 align-top">
                    <div className="font-bold text-[10px]">{issue.label || issue.ref}</div>
                  </td>
                  <td className="px-2 py-2 border border-gray-200 align-top">
                    <SeverityBadge severity={sev} />
                    <p className="mt-1">{issue.issue}</p>
                  </td>
                  <td className="px-2 py-2 border border-gray-200 align-top text-gray-700">
                    {issue.party_a || issue.sell_side || issue.old_text || ''}
                  </td>
                  <td className="px-2 py-2 border border-gray-200 align-top text-gray-700">
                    {issue.party_b || issue.buy_side || issue.new_text || ''}
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
  'claude-sonnet-4-20250514': 'Claude Sonnet 4 — Empfohlen',
  'claude-opus-4-20250514': 'Claude Opus 4 — Premium',
  'claude-haiku-4-5-20251001': 'Claude Haiku 4.5 — Schnell',
};

export default function AiAnalysis({ docId, docName, changeCount, versionA, versionB, onClose }) {
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
  const [userProfile, setUserProfile] = useState('');
  const [showProfileEditor, setShowProfileEditor] = useState(false);
  const [profileInput, setProfileInput] = useState('');
  const [profileSaved, setProfileSaved] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [jobPhase, setJobPhase] = useState('');
  const pollRef = useRef(null);

  // Timer for elapsed seconds during loading
  useEffect(() => {
    if (step !== 'loading') return;
    setElapsed(0);
    const iv = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(iv);
  }, [step]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

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

    fetch(`${API}/ai/user-profile`)
      .then(r => r.json())
      .then(data => setUserProfile(data.profile || ''))
      .catch(() => {});
  }, []);

  const handleSaveProfile = async () => {
    try {
      const resp = await fetch(`${API}/ai/user-profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: profileInput }),
      });
      const data = await resp.json();
      if (data.status === 'ok') {
        setUserProfile(profileInput);
        setShowProfileEditor(false);
        setProfileSaved(true);
        setTimeout(() => setProfileSaved(false), 3000);
      }
    } catch (e) {
      alert('Fehler: ' + e.message);
    }
  };

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
    setJobPhase('Änderungen werden aufbereitet...');
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
        return;
      }

      // If we get a job_id back, start polling
      if (data.job_id) {
        startPolling(data.job_id);
      } else {
        // Direct result (legacy / no-changes case)
        setResult(data);
        setStep('result');
      }
    } catch (e) {
      setError('Verbindungsfehler: ' + e.message);
      setStep('error');
    }
  };

  const startPolling = (jobId) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const resp = await fetch(`${API}/ai/job/${jobId}`);
        const data = await resp.json();

        if (data.error) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setError(data.error);
          setStep('error');
          return;
        }

        if (data.status === 'queued' || data.status === 'running') {
          setJobPhase(data.phase || 'Analyse läuft...');
          return; // keep polling
        }

        // Done — data IS the result
        clearInterval(pollRef.current);
        pollRef.current = null;
        setResult(data);
        setStep('result');
      } catch {
        // Network glitch — keep polling, don't fail
      }
    }, 2000);
  };

  const handleExportDocx = async () => {
    try {
      const body = result.structured
        ? { issue_list: result.issue_list, client_party: result.client_party || clientParty,
            model: result.model, change_count: result.change_count,
            document_context: documentContext }
        : { analysis: result.analysis || result.raw, client_party: result.client_party || clientParty,
            model: result.model, change_count: result.change_count,
            document_context: documentContext };
      const resp = await fetch(`${API}/ai/export-docx`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `IssueList_${result.client_party || clientParty}.docx`;
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
      <div className="bg-white rounded-2xl shadow-2xl max-w-6xl w-full max-h-[90vh] flex flex-col">
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
                Die AI erstellt eine professionelle Issue List mit Ampelsystem (Kritisch / Bedeutend / Redaktionell), 6-Spalten-Tabelle und Handlungsempfehlungen.
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
                        className="text-xs text-violet-600 hover:text-violet-800 underline">Ändern</button>
                    </div>
                  ) : (
                    <div>
                      <label className="block text-xs font-semibold text-violet-800 mb-1">Anthropic API-Key</label>
                      <div className="flex gap-2">
                        <input type="password" value={apiKeyInput}
                          onChange={e => setApiKeyInput(e.target.value)}
                          placeholder="sk-ant-api03-..."
                          className="flex-1 border border-violet-300 rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-violet-500 font-mono"
                          onKeyDown={e => e.key === 'Enter' && handleSaveApiKey()} />
                        <button onClick={handleSaveApiKey}
                          className="px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white rounded text-sm font-medium">Speichern</button>
                        {claudeHasKey && (
                          <button onClick={() => setShowApiKeyInput(false)}
                            className="px-2 py-1.5 text-violet-600 hover:text-violet-800 text-sm">Abbrechen</button>
                        )}
                      </div>
                      <p className="text-[10px] text-violet-500 mt-1">Key von console.anthropic.com — wird lokal gespeichert</p>
                    </div>
                  )}
                </div>
              )}

              {/* AI User Profile */}
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-gray-700">Nutzerprofil (AI-Systemanweisung)</span>
                  <div className="flex items-center gap-2">
                    {profileSaved && <span className="text-xs text-green-600 font-medium">Gespeichert</span>}
                    {!showProfileEditor && (
                      <button onClick={() => { setProfileInput(userProfile); setShowProfileEditor(true); }}
                        className="text-xs text-blue-600 hover:text-blue-800 underline">
                        {userProfile ? 'Bearbeiten' : 'Einrichten'}
                      </button>
                    )}
                  </div>
                </div>
                {!showProfileEditor && userProfile && (
                  <p className="text-[11px] text-gray-500 line-clamp-2">{userProfile.substring(0, 120)}…</p>
                )}
                {!showProfileEditor && !userProfile && (
                  <p className="text-[11px] text-gray-400 italic">Kein Profil hinterlegt — AI verwendet Standard-Systemanweisung.</p>
                )}
                {showProfileEditor && (
                  <div className="mt-2 space-y-2">
                    <textarea rows={5} value={profileInput} onChange={e => setProfileInput(e.target.value)}
                      placeholder="Beschreiben Sie Ihre Rolle, bevorzugte Sprache, Detailtiefe, Zitierstil…"
                      className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs focus:ring-2 focus:ring-blue-500 resize-y" />
                    <div className="flex gap-2">
                      <button onClick={handleSaveProfile}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-medium">Speichern</button>
                      <button onClick={() => setShowProfileEditor(false)}
                        className="px-2 py-1.5 text-gray-600 hover:text-gray-800 text-xs">Abbrechen</button>
                    </div>
                  </div>
                )}
              </div>

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
                <label className="block text-sm font-semibold text-gray-700 mb-1">Beauftragende Partei *</label>
                <input type="text" value={clientParty} onChange={e => setClientParty(e.target.value)}
                  placeholder="z.B. Verkäufer GmbH, Käufer AG, Lizenzgeber, Darlehensnehmer..."
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
                  placeholder="z.B. SPA, SHA, NDA, Lizenzvertrag, Kreditvertrag..."
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
            const numChanges = changeCount || 50;
            let estimatedSeconds;
            if (isClaude) {
              const numBatches = Math.ceil(numChanges / 50);
              estimatedSeconds = numBatches * 18 + 25;
            } else {
              estimatedSeconds = Math.max(120, numChanges * 2);
            }

            const pct = Math.min(95, Math.round((elapsed / estimatedSeconds) * 100));
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            const estMins = Math.ceil(estimatedSeconds / 60);
            const remainSecs = Math.max(0, estimatedSeconds - elapsed);
            const remainMins = Math.floor(remainSecs / 60);
            const remainS = remainSecs % 60;

            return (
              <div className="py-8 space-y-6">
                <div className="text-center">
                  <div className={`inline-block w-10 h-10 border-4 ${isClaude ? 'border-violet-200 border-t-violet-600' : 'border-blue-200 border-t-[#1F3864]'} rounded-full animate-spin mb-3`}></div>
                  <p className="text-gray-700 font-semibold">{jobPhase || 'Analyse läuft...'}</p>
                  <p className="text-gray-400 text-sm mt-1">
                    {mins > 0 ? `${mins}:${secs.toString().padStart(2,'0')}` : `${secs}s`} vergangen
                    {remainSecs > 5 && <span className="ml-2">| ca. {remainMins > 0 ? `${remainMins}:${remainS.toString().padStart(2,'0')}` : `${remainSecs}s`} verbleibend</span>}
                  </p>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                  <div className={`h-full rounded-full transition-all duration-1000 ${isClaude ? 'bg-gradient-to-r from-violet-500 to-violet-600' : 'bg-gradient-to-r from-[#1F3864] to-[#2D5AA0]'}`} style={{width:`${pct}%`}}></div>
                </div>
                <p className="text-center text-xs text-gray-400">
                  {numChanges} Änderungen | Geschätzt ca. {estMins} {estMins === 1 ? 'Minute' : 'Minuten'} ({isClaude ? CLAUDE_MODEL_NAMES[model] || model : model || 'qwen2.5:14b'})
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
                {issueList.filter_note && (
                  <p className="text-xs text-green-300 mt-0.5">{issueList.filter_note}</p>
                )}
              </div>

              {/* Legend */}
              <div className="flex gap-2 text-xs">
                <span className="px-3 py-1 rounded font-semibold" style={{backgroundColor:'#FDEDEC', color:'#991B1B'}}>KRITISCH</span>
                <span className="px-3 py-1 rounded font-semibold" style={{backgroundColor:'#FEF9E7', color:'#92400E'}}>BEDEUTEND</span>
                <span className="px-3 py-1 rounded border border-gray-300 font-semibold text-gray-600">REDAKTIONELL</span>
              </div>

              {/* Summary stats */}
              {summary && (
                <div className="grid grid-cols-3 gap-2">
                  {[['critical','Kritisch','bg-red-50 text-red-800 border-red-200'],
                    ['significant','Bedeutend','bg-yellow-50 text-yellow-800 border-yellow-200'],
                    ['editorial','Redaktionell','bg-gray-50 text-gray-700 border-gray-200'],
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
                <IssueTable key={i} section={sec} clientParty={result.client_party || clientParty} />
              ))}

              {/* Actions */}
              <div className="flex gap-2 pt-2 border-t">
                <button onClick={handleExportDocx}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Als Word speichern (A4 Querformat)
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
                <span>| {result.client_party || clientParty}</span>
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
