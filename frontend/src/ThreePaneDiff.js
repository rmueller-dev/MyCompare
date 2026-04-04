import React, { useRef, useCallback } from 'react';
import DOMPurify from 'dompurify';

function SafeHtml({ html, fallback }) {
  if (!html) return <>{fallback || ''}</>;
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['span', 'div', 'br', 'em', 'b', 'i', 'u', 's', 'strong', 'sub', 'sup'],
    ALLOWED_ATTR: ['style'],
  });
  return <span dangerouslySetInnerHTML={{ __html: clean }} />;
}

export default function ThreePaneDiff({ unifiedLines, filter, colors, changeRefs, currentChangeIndex }) {
  const leftRef = useRef(null);
  const midRef = useRef(null);
  const rightRef = useRef(null);
  const syncing = useRef(false);

  const defaultColors = { insert: '#16a34a', delete: '#dc2626', replace: '#ca8a04' };
  const c = { ...defaultColors, ...colors };

  const handleScroll = useCallback((source) => {
    if (syncing.current) return;
    syncing.current = true;
    const refs = [leftRef, midRef, rightRef];
    const sourceEl = source === 'left' ? leftRef.current : source === 'mid' ? midRef.current : rightRef.current;
    if (!sourceEl) { syncing.current = false; return; }

    const scrollTop = sourceEl.scrollTop;
    const scrollRatio = sourceEl.scrollTop / (sourceEl.scrollHeight - sourceEl.clientHeight || 1);

    refs.forEach(ref => {
      if (ref.current && ref.current !== sourceEl) {
        ref.current.scrollTop = scrollRatio * (ref.current.scrollHeight - ref.current.clientHeight || 1);
      }
    });

    requestAnimationFrame(() => { syncing.current = false; });
  }, []);

  const filteredLines = (unifiedLines || []).filter(line => {
    if (!filter || filter === 'all') return true;
    if (filter === 'formatting') return false; // formatting not in unified lines
    return line.type === filter || line.type === 'equal';
  });

  let changeNum = 0;

  return (
    <div className="border rounded-lg overflow-hidden text-sm font-mono">
      <div className="grid grid-cols-3 bg-gray-100 border-b text-xs font-semibold text-gray-600 uppercase">
        <div className="px-3 py-1.5 border-r">Original (V-A)</div>
        <div className="px-3 py-1.5 border-r text-center">Redline / Änderungen</div>
        <div className="px-3 py-1.5">Geändert (V-B)</div>
      </div>
      <div className="grid grid-cols-3" style={{ height: '60vh' }}>
        {/* Left pane - Original */}
        <div ref={leftRef} className="overflow-auto border-r" onScroll={() => handleScroll('left')}>
          {filteredLines.map((line, i) => {
            const isChange = line.type !== 'equal';
            if (isChange) changeNum++;
            return (
              <div key={i} className={`px-2 py-0.5 whitespace-pre-wrap break-all min-h-[1.5em] ${
                line.type === 'delete' ? 'bg-red-50' : line.type === 'replace' ? 'bg-yellow-50' : ''
              }`}>
                <span className="text-gray-400 text-xs mr-2 select-none inline-block w-8 text-right">
                  {line.left_num || ''}
                </span>
                {line.left_text || ''}
              </div>
            );
          })}
        </div>

        {/* Middle pane - Redline */}
        <div ref={midRef} className="overflow-auto border-r bg-gray-50" onScroll={() => handleScroll('mid')}>
          {(() => { changeNum = 0; return null; })()}
          {filteredLines.map((line, i) => {
            const isChange = line.type !== 'equal';
            if (isChange) changeNum++;
            const refIdx = isChange ? changeNum - 1 : null;
            const isHighlighted = refIdx !== null && refIdx === currentChangeIndex;

            return (
              <div key={i}
                ref={refIdx !== null ? (el) => { if (changeRefs?.current) changeRefs.current[refIdx] = el; } : null}
                className={`px-2 py-0.5 whitespace-pre-wrap break-all min-h-[1.5em] ${
                  isHighlighted ? 'ring-2 ring-blue-400 bg-blue-50' : ''
                }`}
              >
                {isChange && (
                  <span className="text-[10px] font-bold text-gray-400 mr-1">#{changeNum}</span>
                )}
                {line.type === 'equal' ? (
                  <span className="text-gray-600">{line.left_text}</span>
                ) : line.type === 'delete' ? (
                  <span style={{ color: c.delete, textDecoration: 'line-through' }}>{line.left_text}</span>
                ) : line.type === 'insert' ? (
                  <span style={{ color: c.insert, textDecoration: 'underline' }}>{line.right_text}</span>
                ) : line.type === 'replace' ? (
                  <span>
                    <span style={{ color: c.delete, textDecoration: 'line-through' }}>{line.left_text}</span>
                    {' '}
                    <span style={{ color: c.insert, textDecoration: 'underline' }}>{line.right_text}</span>
                  </span>
                ) : line.left_text || line.right_text}
              </div>
            );
          })}
        </div>

        {/* Right pane - Modified */}
        <div ref={rightRef} className="overflow-auto" onScroll={() => handleScroll('right')}>
          {filteredLines.map((line, i) => (
            <div key={i} className={`px-2 py-0.5 whitespace-pre-wrap break-all min-h-[1.5em] ${
              line.type === 'insert' ? 'bg-green-50' : line.type === 'replace' ? 'bg-yellow-50' : ''
            }`}>
              <span className="text-gray-400 text-xs mr-2 select-none inline-block w-8 text-right">
                {line.right_num || ''}
              </span>
              {line.right_text || ''}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
