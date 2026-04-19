import React, { useState, useEffect } from 'react';

const API = '/api';

export default function MultiCompare({ onResult }) {
  const [original, setOriginal] = useState(null);
  const [modifiedFiles, setModifiedFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [results, setResults] = useState(null);
  const [activeTab, setActiveTab] = useState(0);

  const ALLOWED = ['.docx', '.xlsx', '.pptx', '.pdf', '.rtf', '.txt', '.html', '.htm'];
  const isAllowed = (name) => ALLOWED.some(ext => name.toLowerCase().endsWith(ext));

  const handleOriginal = (e) => {
    const file = e.target.files?.[0];
    if (file && isAllowed(file.name)) {
      setOriginal(file);
      setError('');
    } else {
      setError('Nicht unterstuetzter Dateityp');
    }
  };

  const handleModified = (e) => {
    const files = Array.from(e.target.files || []).filter(f => isAllowed(f.name));
    if (files.length === 0) {
      setError('Keine unterstuetzten Dateien ausgewaehlt');
      return;
    }
    if (files.length > 5) {
      setError('Maximal 5 modifizierte Versionen erlaubt');
      return;
    }
    setModifiedFiles(files);
    setError('');
  };

  const runCompare = async () => {
    if (!original || modifiedFiles.length === 0) return;
    setLoading(true);
    setError('');
    setResults(null);

    const formData = new FormData();
    formData.append('file_original', original);
    modifiedFiles.forEach((f, i) => {
      formData.append(`file_modified_${i + 1}`, f);
    });

    try {
      const res = await fetch(`${API}/multi-compare`, { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Vergleich fehlgeschlagen');
      setResults(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const typeColors = {
    replace: 'bg-yellow-100 text-yellow-800',
    insert: 'bg-green-100 text-green-800',
    delete: 'bg-red-100 text-red-800',
    formatting: 'bg-purple-100 text-purple-800',
  };
  const typeLabels = {
    replace: 'Geaendert',
    insert: 'Eingefuegt',
    delete: 'Geloescht',
    formatting: 'Formatierung',
  };

  return (
    <div className="space-y-4">
      <div className="bg-white border rounded-xl p-6">
        <h2 className="text-lg font-bold text-gray-800 mb-4">1:Many Vergleich</h2>
        <p className="text-sm text-gray-500 mb-4">
          Vergleichen Sie ein Original gegen bis zu 5 modifizierte Versionen gleichzeitig.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          {/* Original file */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Original</label>
            <input type="file" onChange={handleOriginal}
              accept=".docx,.xlsx,.pptx,.pdf,.rtf,.txt,.html,.htm"
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" />
            {original && <p className="text-xs text-green-600 mt-1">{original.name}</p>}
          </div>

          {/* Modified files */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Modifizierte Versionen (max. 5)
            </label>
            <input type="file" multiple onChange={handleModified}
              accept=".docx,.xlsx,.pptx,.pdf,.rtf,.txt,.html,.htm"
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100" />
            {modifiedFiles.length > 0 && (
              <p className="text-xs text-green-600 mt-1">
                {modifiedFiles.length} Datei(en): {modifiedFiles.map(f => f.name).join(', ')}
              </p>
            )}
          </div>
        </div>

        {error && <p className="text-sm text-red-600 mb-2">{error}</p>}

        <button onClick={runCompare}
          disabled={!original || modifiedFiles.length === 0 || loading}
          className="px-6 py-2.5 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">
          {loading ? 'Vergleich laeuft...' : 'Vergleich starten'}
        </button>
      </div>

      {/* Results */}
      {results && (
        <div className="bg-white border rounded-xl p-6">
          <h3 className="text-lg font-bold text-gray-800 mb-2">
            Ergebnisse: {results.original_filename} vs. {results.file_count} Versionen
          </h3>

          {/* Total statistics */}
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-4">
            {[
              ['Gesamt', results.total_stats.total_changes, 'bg-gray-100'],
              ['Hinzugefuegt', results.total_stats.additions, 'bg-green-100'],
              ['Geloescht', results.total_stats.deletions, 'bg-red-100'],
              ['Ersetzt', results.total_stats.replacements, 'bg-yellow-100'],
              ['Verschoben', results.total_stats.moves, 'bg-blue-100'],
              ['Formatierung', results.total_stats.formatting, 'bg-purple-100'],
            ].map(([label, count, bg]) => (
              <div key={label} className={`${bg} rounded-lg p-2 text-center`}>
                <div className="text-lg font-bold">{count}</div>
                <div className="text-xs text-gray-600">{label}</div>
              </div>
            ))}
          </div>

          {/* Tabs for each comparison */}
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-4 flex-wrap">
            <button onClick={() => setActiveTab(-1)}
              className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                activeTab === -1 ? 'bg-white shadow text-gray-800' : 'text-gray-500 hover:text-gray-700'
              }`}>
              Alle zusammen
            </button>
            {results.comparisons.map((comp, i) => (
              <button key={i} onClick={() => setActiveTab(i)}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  activeTab === i ? 'bg-white shadow text-gray-800' : 'text-gray-500 hover:text-gray-700'
                }`}>
                {comp.filename}
                <span className="ml-1 text-gray-400">({comp.summary?.total_changes || 0})</span>
              </button>
            ))}
          </div>

          {/* Display changes */}
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {(activeTab === -1 ? results.merged_changes : (results.comparisons[activeTab]?.structural_changes || []))
              .map((ch, i) => (
                <div key={i} className="border rounded p-3 bg-white">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${typeColors[ch.type] || 'bg-gray-100'}`}>
                      {typeLabels[ch.type] || ch.type}
                    </span>
                    <span className="text-xs text-gray-500">{ch.location}</span>
                    {ch.source_file && activeTab === -1 && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700">
                        {ch.source_file}
                      </span>
                    )}
                  </div>
                  {ch.old_items && (
                    <div className="flex gap-2 text-xs">
                      <div className="flex-1 bg-red-50 p-1.5 rounded">
                        {ch.old_items.map((it, j) => <div key={j}>{it.text}</div>)}
                      </div>
                      {ch.new_items && (
                        <div className="flex-1 bg-green-50 p-1.5 rounded">
                          {ch.new_items.map((it, j) => <div key={j}>{it.text}</div>)}
                        </div>
                      )}
                    </div>
                  )}
                  {ch.formatting_changes && (
                    <div className="text-xs text-purple-700 mt-1">
                      {ch.formatting_changes.map((fc, j) => <div key={j}>* {fc}</div>)}
                    </div>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
