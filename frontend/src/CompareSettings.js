import React, { useState } from 'react';

export default function CompareSettings({ options, onChange }) {
  const [open, setOpen] = useState(false);

  const toggle = (key) => {
    onChange({ ...options, [key]: !options[key] });
  };

  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-sm font-medium text-gray-600 hover:text-gray-800 transition-colors"
      >
        <svg className={`w-4 h-4 transition-transform ${open ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
        </svg>
        Vergleichsoptionen
        {(options.ignore_whitespace || options.ignore_case || options.ignore_headers_footers) && (
          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">aktiv</span>
        )}
      </button>

      {open && (
        <div className="mt-2 bg-gray-50 border rounded-lg p-4 space-y-3">
          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={options.ignore_whitespace || false}
              onChange={() => toggle('ignore_whitespace')}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
            <div>
              <div className="text-sm font-medium text-gray-700">Leerzeichen ignorieren</div>
              <div className="text-xs text-gray-500">Mehrfache Leerzeichen und Einrückungen werden nicht als Änderung gewertet</div>
            </div>
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={options.ignore_case || false}
              onChange={() => toggle('ignore_case')}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
            <div>
              <div className="text-sm font-medium text-gray-700">Groß-/Kleinschreibung ignorieren</div>
              <div className="text-xs text-gray-500">Unterschiede in der Schreibweise werden ignoriert</div>
            </div>
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={options.ignore_headers_footers || false}
              onChange={() => toggle('ignore_headers_footers')}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
            <div>
              <div className="text-sm font-medium text-gray-700">Kopf-/Fußzeilen ignorieren</div>
              <div className="text-xs text-gray-500">Änderungen in Kopf- und Fußzeilen werden nicht angezeigt (nur DOCX)</div>
            </div>
          </label>

          <div className="pt-2 text-xs text-gray-400">
            Änderungen an den Optionen lösen einen neuen Vergleich aus.
          </div>
        </div>
      )}
    </div>
  );
}
