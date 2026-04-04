import React from 'react';

const FILTERS = [
  { key: 'all', label: 'Alle', color: 'bg-gray-100 text-gray-800' },
  { key: 'insert', label: 'Einfügungen', color: 'bg-green-100 text-green-800' },
  { key: 'delete', label: 'Löschungen', color: 'bg-red-100 text-red-800' },
  { key: 'replace', label: 'Ersetzungen', color: 'bg-yellow-100 text-yellow-800' },
  { key: 'formatting', label: 'Formatierung', color: 'bg-purple-100 text-purple-800' },
];

export default function ChangeFilters({ activeFilter, onFilterChange }) {
  return (
    <div className="flex flex-wrap gap-1.5 mb-4">
      <span className="text-xs text-gray-500 self-center mr-1">Filter:</span>
      {FILTERS.map(f => (
        <button
          key={f.key}
          onClick={() => onFilterChange(f.key)}
          className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
            activeFilter === f.key
              ? f.color + ' ring-2 ring-offset-1 ring-gray-400 shadow-sm'
              : 'bg-gray-50 text-gray-500 hover:bg-gray-100'
          }`}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
