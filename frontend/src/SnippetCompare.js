import React, { useState } from 'react';

const API = '/api';

export default function SnippetCompare({ onResult }) {
  const [textA, setTextA] = useState('');
  const [textB, setTextB] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [ignoreWhitespace, setIgnoreWhitespace] = useState(false);
  const [ignoreCase, setIgnoreCase] = useState(false);

  const runCompare = async () => {
    if (!textA && !textB) {
      setError('Bitte mindestens einen Text eingeben');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API}/snippet-compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text_a: textA,
          text_b: textB,
          ignore_whitespace: ignoreWhitespace,
          ignore_case: ignoreCase,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Vergleich fehlgeschlagen');
      onResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto">
      <h2 className="text-xl font-bold text-gray-800 mb-4">Text-Vergleich (Snippet)</h2>
      <p className="text-sm text-gray-500 mb-4">
        Vergleichen Sie zwei Textausschnitte direkt — ohne Datei-Upload.
      </p>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Text A (alt)</label>
          <textarea
            value={textA}
            onChange={(e) => setTextA(e.target.value)}
            className="w-full h-64 border rounded-lg p-3 text-sm font-mono resize-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="Alten Text hier einfügen..."
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Text B (neu)</label>
          <textarea
            value={textB}
            onChange={(e) => setTextB(e.target.value)}
            className="w-full h-64 border rounded-lg p-3 text-sm font-mono resize-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="Neuen Text hier einfügen..."
          />
        </div>
      </div>

      <div className="flex items-center gap-6 mb-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={ignoreWhitespace} onChange={(e) => setIgnoreWhitespace(e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 text-blue-600" />
          Leerzeichen ignorieren
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={ignoreCase} onChange={(e) => setIgnoreCase(e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 text-blue-600" />
          Groß-/Kleinschreibung ignorieren
        </label>
      </div>

      {error && (
        <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 p-3 rounded-lg">{error}</div>
      )}

      <button
        onClick={runCompare}
        disabled={loading || (!textA && !textB)}
        className="bg-blue-600 text-white px-6 py-2.5 rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors"
      >
        {loading ? 'Vergleiche...' : 'Texte vergleichen'}
      </button>
    </div>
  );
}
