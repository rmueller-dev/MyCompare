import React, { useState, useEffect } from 'react';

const API = '/api';

export default function AiAnalysis({ docId, versionA, versionB, onClose }) {
  const [step, setStep] = useState('form'); // 'form' | 'loading' | 'result' | 'error'
  const [clientParty, setClientParty] = useState('');
  const [clientVersion, setClientVersion] = useState('a'); // 'a' = Version A is client's, 'b' = Version B
  const [documentContext, setDocumentContext] = useState('');
  const [model, setModel] = useState('');
  const [models, setModels] = useState([]);
  const [ollamaAvailable, setOllamaAvailable] = useState(null);
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
        setModels(data.models || []);
        if (data.models?.length > 0) setModel(data.models[0]);
      })
      .catch(() => setOllamaAvailable(false));
  }, []);

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

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b bg-gradient-to-r from-violet-600 to-purple-600 rounded-t-2xl">
          <div className="flex items-center gap-3">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
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
          {ollamaAvailable === false && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
              <p className="text-red-800 font-semibold">Ollama nicht erreichbar</p>
              <p className="text-red-600 text-sm mt-1">
                Bitte starten Sie Ollama (<a href="https://ollama.ai" target="_blank" rel="noreferrer" className="underline">ollama.ai</a>) und laden Sie ein Modell:
                <code className="bg-red-100 px-1 rounded ml-1">ollama pull llama3.1</code>
              </p>
            </div>
          )}

          {step === 'form' && (
            <div className="space-y-4">
              <p className="text-gray-600 text-sm">
                Die AI analysiert die Änderungen aus Sicht Ihres Mandanten und erstellt eine strukturierte Issue List mit Bewertungen und Empfehlungen.
              </p>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">
                  Wen vertreten Sie? *
                </label>
                <input
                  type="text"
                  value={clientParty}
                  onChange={e => setClientParty(e.target.value)}
                  placeholder="z.B. Käufer, Verkäufer GmbH, Mieter, Lizenzgeber..."
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500 focus:border-violet-500"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">
                  Welche Version ist Ihre? *
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setClientVersion('a')}
                    className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      clientVersion === 'a'
                        ? 'bg-violet-100 border-violet-500 text-violet-800'
                        : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    Version A (V{versionA})
                    <span className="block text-xs mt-0.5 opacity-70">Vorversion — Standard</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setClientVersion('b')}
                    className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                      clientVersion === 'b'
                        ? 'bg-violet-100 border-violet-500 text-violet-800'
                        : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    Version B (V{versionB})
                    <span className="block text-xs mt-0.5 opacity-70">Aktuelle Version</span>
                  </button>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                  Die Gegenseite hat die andere Version erstellt. Änderungen werden aus Ihrer Sicht bewertet.
                </p>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1">
                  Dokumenttyp (optional)
                </label>
                <input
                  type="text"
                  value={documentContext}
                  onChange={e => setDocumentContext(e.target.value)}
                  placeholder="z.B. Kaufvertrag, Mietvertrag, Lizenzvertrag, NDA..."
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500 focus:border-violet-500"
                />
              </div>

              {models.length > 0 && (
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1">
                    AI-Modell
                  </label>
                  <select
                    value={model}
                    onChange={e => setModel(e.target.value)}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500 focus:border-violet-500"
                  >
                    {models.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
              )}

              <button
                onClick={handleAnalyze}
                disabled={!clientParty.trim() || !ollamaAvailable}
                className="w-full bg-violet-600 hover:bg-violet-700 disabled:bg-gray-300 text-white font-semibold py-2.5 rounded-lg transition-colors"
              >
                Issue List generieren
              </button>
            </div>
          )}

          {step === 'loading' && (() => {
            const estimatedSec = 180; // ~3 min estimate
            const pct = Math.min(95, Math.round((elapsed / estimatedSec) * 100));
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            const phases = [
              [0, 'Änderungen werden aufbereitet...'],
              [10, 'Prompt wird an LLM gesendet...'],
              [20, 'AI analysiert die Klauseln...'],
              [40, 'Risikobewertung läuft...'],
              [60, 'Issue List wird erstellt...'],
              [80, 'Empfehlungen werden formuliert...'],
              [90, 'Analyse wird abgeschlossen...'],
            ];
            const phase = [...phases].reverse().find(([p]) => pct >= p)?.[1] || phases[0][1];
            return (
              <div className="py-8 space-y-6">
                <div className="text-center">
                  <div className="inline-block w-10 h-10 border-4 border-violet-200 border-t-violet-600 rounded-full animate-spin mb-3"></div>
                  <p className="text-gray-700 font-semibold">{phase}</p>
                  <p className="text-gray-400 text-sm mt-1">
                    {mins > 0 ? `${mins}:${secs.toString().padStart(2, '0')}` : `${secs}s`} vergangen
                  </p>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-violet-500 to-purple-600 rounded-full transition-all duration-1000 ease-out"
                    style={{ width: `${pct}%` }}
                  ></div>
                </div>
                <p className="text-center text-xs text-gray-400">
                  Geschätzt ca. 2-3 Minuten mit {model || 'qwen2.5:14b'}
                </p>
              </div>
            );
          })()}

          {step === 'error' && (
            <div className="space-y-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-800">{error}</p>
              </div>
              <button
                onClick={() => setStep('form')}
                className="text-violet-600 hover:text-violet-800 text-sm font-medium"
              >
                &larr; Zurück zum Formular
              </button>
            </div>
          )}

          {step === 'result' && result && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span className="bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full text-xs font-medium">
                  {result.model}
                </span>
                <span>{result.change_count} Änderungen analysiert</span>
                {result.truncated && (
                  <span className="text-amber-600">
                    (von {result.total_changes} — auf 100 begrenzt)
                  </span>
                )}
                <span>• Mandant: {result.client_party}</span>
              </div>

              <div className="bg-gray-50 border rounded-lg p-4 prose prose-sm max-w-none overflow-x-auto">
                <pre className="whitespace-pre-wrap text-sm text-gray-800 font-sans leading-relaxed">
                  {result.analysis}
                </pre>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    try {
                      const resp = await fetch(`${API}/ai/export-docx`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                          analysis: result.analysis,
                          client_party: result.client_party,
                          model: result.model,
                          change_count: result.change_count,
                        }),
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
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Als Word speichern
                </button>
                <button
                  onClick={() => { setStep('form'); setResult(null); }}
                  className="px-4 py-2 border border-gray-300 hover:bg-gray-50 rounded-lg text-sm font-medium text-gray-700 transition-colors"
                >
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
