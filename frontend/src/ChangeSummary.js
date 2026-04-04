import React from 'react';

export default function ChangeSummary({ summary, colors }) {
  if (!summary) return null;

  const defaultColors = {
    insert: '#16a34a',
    delete: '#dc2626',
    replace: '#ca8a04',
    formatting: '#9333ea',
  };
  const c = { ...defaultColors, ...colors };

  const items = [
    { label: 'Einfügungen', count: summary.insert_count || 0, color: c.insert, bg: '#f0fdf4' },
    { label: 'Löschungen', count: summary.delete_count || 0, color: c.delete, bg: '#fef2f2' },
    { label: 'Ersetzungen', count: summary.replace_count || 0, color: c.replace, bg: '#fefce8' },
    { label: 'Formatierung', count: summary.formatting_count || 0, color: c.formatting, bg: '#faf5ff' },
  ];

  const total = items.reduce((s, i) => s + i.count, 0);

  return (
    <div className="bg-white border rounded-xl p-4 mb-4">
      <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wider mb-3">
        Änderungsübersicht — {total} Änderung{total !== 1 ? 'en' : ''} erkannt
      </h3>
      <div className="flex flex-wrap gap-3">
        {items.map(item => (
          <div key={item.label} className="flex items-center gap-2 px-3 py-2 rounded-lg"
            style={{ backgroundColor: item.bg }}>
            <span className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }}></span>
            <span className="text-sm font-medium" style={{ color: item.color }}>{item.count}</span>
            <span className="text-sm text-gray-600">{item.label}</span>
          </div>
        ))}
      </div>
      {summary.total_lines_a != null && (
        <div className="mt-2 text-xs text-gray-400">
          Zeilen: {summary.total_lines_a} (alt) → {summary.total_lines_b} (neu) |
          Strukturelle Änderungen: {summary.structural_count} | Plaintext: {summary.plaintext_count}
        </div>
      )}
    </div>
  );
}
