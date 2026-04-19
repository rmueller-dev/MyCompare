import React from 'react';

export default function ChangeNavigation({ currentIndex, totalChanges, onNavigate }) {
  if (totalChanges === 0) return null;

  const display = currentIndex >= 0 ? currentIndex + 1 : '—';

  return (
    <div className="flex items-center gap-2 bg-white border rounded-lg px-3 py-2 mb-4 shadow-sm">
      <span className="text-xs text-gray-500 mr-1">Navigation:</span>
      <button
        onClick={() => onNavigate(Math.max(0, (currentIndex || 0) - 1))}
        disabled={currentIndex <= 0}
        className="w-8 h-8 flex items-center justify-center rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed text-gray-700 text-sm font-bold"
        title="Vorherige Änderung"
      >
        ‹
      </button>
      <span className="text-sm font-medium text-gray-700 min-w-[80px] text-center">
        {display} / {totalChanges}
      </span>
      <button
        onClick={() => onNavigate(Math.min(totalChanges - 1, (currentIndex || 0) + 1))}
        disabled={currentIndex >= totalChanges - 1}
        className="w-8 h-8 flex items-center justify-center rounded bg-gray-100 hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed text-gray-700 text-sm font-bold"
        title="Nächste Änderung"
      >
        ›
      </button>
      <span className="text-xs text-gray-400 ml-2">
        Tastatur: ↑/↓ oder J/K
      </span>
    </div>
  );
}
