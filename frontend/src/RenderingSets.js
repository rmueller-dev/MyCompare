import React, { useState, useEffect } from 'react';

const API = '/api';

export default function RenderingSets({ onApply }) {
  const [sets, setSets] = useState([]);
  const [editing, setEditing] = useState(null);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState('');

  const fetchSets = async () => {
    try {
      const res = await fetch(`${API}/rendering-sets`);
      const data = await res.json();
      setSets(data);
    } catch (err) {
      setError('Fehler beim Laden der Profile');
    }
  };

  useEffect(() => { fetchSets(); }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError('');
    try {
      const res = await fetch(`${API}/rendering-sets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName,
          description: newDesc,
          settings: {
            colors: {
              deletion: '#DC2626',
              insertion: '#2563EB',
              move: '#16A34A',
              formatting: '#E65100',
              table: '#00695C',
            },
            markup: {
              deletion_style: 'strikethrough',
              insertion_style: 'double-underline',
              move_style: 'strikethrough',
            },
            options: {
              ignore_whitespace: false,
              ignore_case: false,
              ignore_headers_footers: false,
              character_level: false,
              compare_images: true,
              compare_formatting: true,
            },
          },
        }),
      });
      if (!res.ok) throw new Error((await res.json()).error);
      setNewName('');
      setNewDesc('');
      setShowCreate(false);
      fetchSets();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (id) => {
    try {
      const res = await fetch(`${API}/rendering-sets/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error((await res.json()).error);
      fetchSets();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSetDefault = async (id) => {
    try {
      await fetch(`${API}/rendering-sets/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_default: true }),
      });
      fetchSets();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleApply = (rs) => {
    if (onApply) {
      onApply(rs.settings);
    }
  };

  const handleUpdateColors = async (rs, colorKey, value) => {
    const updated = { ...rs.settings };
    updated.colors = { ...updated.colors, [colorKey]: value };
    try {
      await fetch(`${API}/rendering-sets/${rs.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: updated }),
      });
      fetchSets();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUpdateOption = async (rs, optKey, value) => {
    const updated = { ...rs.settings };
    updated.options = { ...updated.options, [optKey]: value };
    try {
      await fetch(`${API}/rendering-sets/${rs.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: updated }),
      });
      fetchSets();
    } catch (err) {
      setError(err.message);
    }
  };

  const colorLabels = {
    deletion: 'Loeschung',
    insertion: 'Einfuegung',
    move: 'Verschiebung',
    formatting: 'Formatierung',
    table: 'Tabelle',
  };

  const optionLabels = {
    ignore_whitespace: 'Leerzeichen ignorieren',
    ignore_case: 'Gross-/Kleinschreibung ignorieren',
    ignore_headers_footers: 'Kopf-/Fusszeilen ignorieren',
    character_level: 'Zeichenebene-Vergleich',
    compare_images: 'Bilder vergleichen',
    compare_formatting: 'Formatierung vergleichen',
  };

  return (
    <div className="bg-white border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wider">
          Vergleichsprofile
        </h3>
        <button onClick={() => setShowCreate(!showCreate)}
          className="text-xs px-3 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200">
          + Neues Profil
        </button>
      </div>

      {error && <p className="text-xs text-red-600 mb-2">{error}</p>}

      {showCreate && (
        <div className="border rounded-lg p-3 mb-3 bg-gray-50">
          <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
            placeholder="Profilname"
            className="w-full text-sm border rounded px-2 py-1 mb-2" />
          <input type="text" value={newDesc} onChange={e => setNewDesc(e.target.value)}
            placeholder="Beschreibung (optional)"
            className="w-full text-sm border rounded px-2 py-1 mb-2" />
          <div className="flex gap-2">
            <button onClick={handleCreate}
              className="text-xs px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700">
              Erstellen
            </button>
            <button onClick={() => setShowCreate(false)}
              className="text-xs px-3 py-1 rounded bg-gray-200 text-gray-700 hover:bg-gray-300">
              Abbrechen
            </button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {sets.map(rs => (
          <div key={rs.id} className={`border rounded-lg p-3 ${rs.is_default ? 'border-blue-300 bg-blue-50' : 'bg-white'}`}>
            <div className="flex items-center justify-between mb-2">
              <div>
                <span className="font-medium text-sm">{rs.name}</span>
                {rs.is_default && (
                  <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-blue-200 text-blue-800">Standard</span>
                )}
                {rs.description && <p className="text-xs text-gray-500">{rs.description}</p>}
              </div>
              <div className="flex gap-1">
                <button onClick={() => handleApply(rs)}
                  className="text-xs px-2 py-1 rounded bg-green-50 text-green-700 hover:bg-green-100 border border-green-200"
                  title="Profil anwenden">
                  Anwenden
                </button>
                {!rs.is_default && (
                  <>
                    <button onClick={() => handleSetDefault(rs.id)}
                      className="text-xs px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200"
                      title="Als Standard setzen">
                      Standard
                    </button>
                    <button onClick={() => handleDelete(rs.id)}
                      className="text-xs px-2 py-1 rounded bg-red-50 text-red-700 hover:bg-red-100 border border-red-200"
                      title="Loeschen">
                      X
                    </button>
                  </>
                )}
                <button onClick={() => setEditing(editing === rs.id ? null : rs.id)}
                  className="text-xs px-2 py-1 rounded bg-gray-50 text-gray-700 hover:bg-gray-100 border border-gray-200">
                  {editing === rs.id ? 'Zuklappen' : 'Bearbeiten'}
                </button>
              </div>
            </div>

            {editing === rs.id && (
              <div className="border-t pt-2 mt-2">
                {/* Colors */}
                <div className="mb-2">
                  <div className="text-xs font-medium text-gray-600 mb-1">Farben</div>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                    {Object.entries(colorLabels).map(([key, label]) => (
                      <label key={key} className="flex items-center gap-1 text-xs">
                        <input type="color"
                          value={rs.settings?.colors?.[key] || '#000000'}
                          onChange={e => handleUpdateColors(rs, key, e.target.value)}
                          className="w-6 h-6 rounded cursor-pointer" />
                        {label}
                      </label>
                    ))}
                  </div>
                </div>

                {/* Options */}
                <div>
                  <div className="text-xs font-medium text-gray-600 mb-1">Optionen</div>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-1">
                    {Object.entries(optionLabels).map(([key, label]) => (
                      <label key={key} className="flex items-center gap-1 text-xs cursor-pointer">
                        <input type="checkbox"
                          checked={rs.settings?.options?.[key] || false}
                          onChange={e => handleUpdateOption(rs, key, e.target.checked)}
                          className="rounded" />
                        {label}
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
