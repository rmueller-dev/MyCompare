import React, { useState } from 'react';

const DEFAULT_COLORS = {
  insert: '#16a34a',
  delete: '#dc2626',
  replace: '#ca8a04',
  formatting: '#9333ea',
};

const PRESETS = [
  { name: 'Standard', colors: { insert: '#16a34a', delete: '#dc2626', replace: '#ca8a04', formatting: '#9333ea' } },
  { name: 'Klassisch', colors: { insert: '#2563eb', delete: '#dc2626', replace: '#d97706', formatting: '#7c3aed' } },
  { name: 'Dezent', colors: { insert: '#059669', delete: '#9f1239', replace: '#92400e', formatting: '#6b21a8' } },
];

const LABELS = {
  insert: 'Einfügungen',
  delete: 'Löschungen',
  replace: 'Ersetzungen',
  formatting: 'Formatierung',
};

export default function ColorConfig({ colors, onChange }) {
  const [open, setOpen] = useState(false);
  const c = { ...DEFAULT_COLORS, ...colors };

  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-800 transition-colors"
      >
        <svg className={`w-4 h-4 transition-transform ${open ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
        </svg>
        Farben anpassen
      </button>

      {open && (
        <div className="mt-2 bg-gray-50 border rounded-lg p-4">
          <div className="flex gap-2 mb-4">
            {PRESETS.map(p => (
              <button key={p.name} onClick={() => onChange(p.colors)}
                className="text-xs px-3 py-1.5 rounded-lg border hover:bg-white transition-colors">
                <div className="flex gap-1 mb-1">
                  {Object.values(p.colors).map((col, i) => (
                    <span key={i} className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: col }}></span>
                  ))}
                </div>
                {p.name}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            {Object.entries(LABELS).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2">
                <input
                  type="color"
                  value={c[key]}
                  onChange={(e) => onChange({ ...c, [key]: e.target.value })}
                  className="w-8 h-8 rounded border cursor-pointer"
                />
                <span className="text-sm text-gray-700">{label}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export { DEFAULT_COLORS };
