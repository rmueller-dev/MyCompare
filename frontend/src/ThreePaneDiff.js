import React, { useRef, useCallback, useState } from 'react';
import DOMPurify from 'dompurify';

function SafeHtml({ html, fallback }) {
  if (!html) return <>{fallback || ''}</>;
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['span', 'div', 'br', 'em', 'b', 'i', 'u', 's', 'strong', 'sub', 'sup'],
    ALLOWED_ATTR: ['style'],
  });
  return <span dangerouslySetInnerHTML={{ __html: clean }} />;
}

/**
 * InlineRedline: renders word-level inline diff in MS-Word/Litera style.
 * Unchanged context shown normally, deleted tokens struck through in red,
 * inserted tokens underlined in blue — all inline within the same line.
 */
function InlineRedline({ segments, deleteColor, insertColor, moveColor }) {
  if (!segments || segments.length === 0) return null;
  return (
    <>
      {segments.map((seg, i) => {
        if (seg.type === 'equal') {
          return <span key={i}>{(seg.old_tokens || []).join('')}</span>;
        }
        if (seg.type === 'delete') {
          return (
            <span key={i} style={{ color: deleteColor || '#dc2626', textDecoration: 'line-through' }}>
              {(seg.old_tokens || []).join('')}
            </span>
          );
        }
        if (seg.type === 'insert') {
          return (
            <span key={i} style={{ color: insertColor || '#2563eb', textDecoration: 'underline' }}>
              {(seg.new_tokens || []).join('')}
            </span>
          );
        }
        if (seg.type === 'replace') {
          return (
            <span key={i}>
              <span style={{ color: deleteColor || '#dc2626', textDecoration: 'line-through' }}>
                {(seg.old_tokens || []).join('')}
              </span>
              <span style={{ color: insertColor || '#2563eb', textDecoration: 'underline' }}>
                {(seg.new_tokens || []).join('')}
              </span>
            </span>
          );
        }
        return null;
      })}
    </>
  );
}

export default function ThreePaneDiff({ unifiedLines, filter, colors, changeRefs, currentChangeIndex }) {
  const leftRef = useRef(null);
  const midRef = useRef(null);
  const rightRef = useRef(null);
  const syncing = useRef(false);
  const [hoveredMoveId, setHoveredMoveId] = useState(null);

  const defaultColors = { insert: '#2563eb', delete: '#dc2626', replace: '#ca8a04', move: '#16a34a' };
  const c = { ...defaultColors, ...colors };

  const handleScroll = useCallback((source) => {
    if (syncing.current) return;
    syncing.current = true;
    const refs = [leftRef, midRef, rightRef];
    const sourceEl = source === 'left' ? leftRef.current : source === 'mid' ? midRef.current : rightRef.current;
    if (!sourceEl) { syncing.current = false; return; }

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
    if (filter === 'formatting') return false;
    const t = line.type;
    // 'replace', 'delete', 'insert', 'move_out', 'move_in' all count as changes
    const isChange = t !== 'equal';
    if (filter === 'replace') return t === 'replace' || t === 'equal';
    if (filter === 'delete') return t === 'delete' || t === 'move_out' || t === 'equal';
    if (filter === 'insert') return t === 'insert' || t === 'move_in' || t === 'equal';
    return t === filter || t === 'equal';
  });

  let changeNum = 0;

  const moveLineStyle = (line, side) => {
    const isMoveType = line.type === 'move_out' || line.type === 'move_in';
    if (!isMoveType) return {};
    const isHovered = hoveredMoveId !== null && hoveredMoveId === line.moveId;
    return {
      backgroundColor: isHovered ? 'rgba(22,163,74,0.25)' : 'rgba(22,163,74,0.08)',
      cursor: 'pointer',
    };
  };

  const moveMidContent = (line) => {
    const isHovered = hoveredMoveId !== null && hoveredMoveId === line.moveId;
    const baseStyle = {
      color: c.move,
      backgroundColor: isHovered ? 'rgba(22,163,74,0.18)' : 'transparent',
      borderRadius: '2px',
      padding: '0 1px',
    };
    if (line.type === 'move_out') {
      return (
        <span style={baseStyle} title={`Verschoben (ID ${line.moveId}) — zur Zielposition scrollen`}>
          {line.inner_diff && line.inner_diff.length > 0 ? (
            <span style={{ textDecoration: 'line-through' }}>
              <InlineRedline
                segments={line.inner_diff}
                deleteColor={c.delete}
                insertColor={c.insert}
              />
            </span>
          ) : (
            <span style={{ textDecoration: 'line-through' }}>{line.left_text}</span>
          )}
          {' '}
          <span style={{ fontSize: '10px', fontWeight: 700 }}>↓Verschoben</span>
        </span>
      );
    }
    if (line.type === 'move_in') {
      return (
        <span style={baseStyle} title={`Verschoben von (ID ${line.moveId}) — zur Quellposition scrollen`}>
          <span style={{ fontSize: '10px', fontWeight: 700 }}>↑Verschoben </span>
          {line.inner_diff && line.inner_diff.length > 0 ? (
            <span style={{ textDecoration: 'underline' }}>
              <InlineRedline
                segments={line.inner_diff}
                deleteColor={c.delete}
                insertColor={c.insert}
              />
            </span>
          ) : (
            <span style={{ textDecoration: 'underline' }}>{line.right_text}</span>
          )}
        </span>
      );
    }
    return null;
  };

  return (
    <div className="border rounded-lg overflow-hidden text-sm font-mono">
      {/* Legend */}
      <div className="flex gap-4 px-3 py-1.5 bg-gray-50 border-b text-xs text-gray-500">
        <span style={{ color: c.delete, textDecoration: 'line-through' }}>Gelöscht</span>
        <span style={{ color: c.insert, textDecoration: 'underline' }}>Eingefügt</span>
        <span style={{ color: c.move }}>⇅ Verschoben</span>
      </div>

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
            const isMoveType = line.type === 'move_out' || line.type === 'move_in';
            return (
              <div
                key={i}
                className={`px-2 py-0.5 whitespace-pre-wrap break-all min-h-[1.5em] ${
                  line.type === 'delete' ? 'bg-red-50' : line.type === 'replace' ? 'bg-yellow-50' : ''
                }`}
                style={moveLineStyle(line, 'left')}
                onMouseEnter={isMoveType ? () => setHoveredMoveId(line.moveId) : undefined}
                onMouseLeave={isMoveType ? () => setHoveredMoveId(null) : undefined}
              >
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
            const isMoveType = line.type === 'move_out' || line.type === 'move_in';

            return (
              <div key={i}
                ref={refIdx !== null ? (el) => { if (changeRefs?.current) changeRefs.current[refIdx] = el; } : null}
                data-move-id={isMoveType ? line.moveId : undefined}
                className={`px-2 py-0.5 whitespace-pre-wrap break-all min-h-[1.5em] ${
                  isHighlighted ? 'ring-2 ring-blue-400 bg-blue-50' : ''
                }`}
                style={isMoveType ? moveLineStyle(line, 'mid') : {}}
                onMouseEnter={isMoveType ? () => setHoveredMoveId(line.moveId) : undefined}
                onMouseLeave={isMoveType ? () => setHoveredMoveId(null) : undefined}
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
                  line.inline_diff && line.inline_diff.length > 0 ? (
                    <InlineRedline
                      segments={line.inline_diff}
                      deleteColor={c.delete}
                      insertColor={c.insert}
                    />
                  ) : (
                    <span>
                      <span style={{ color: c.delete, textDecoration: 'line-through' }}>{line.left_text}</span>
                      {' '}
                      <span style={{ color: c.insert, textDecoration: 'underline' }}>{line.right_text}</span>
                    </span>
                  )
                ) : isMoveType ? (
                  moveMidContent(line)
                ) : (line.left_text || line.right_text)}
              </div>
            );
          })}
        </div>

        {/* Right pane - Modified */}
        <div ref={rightRef} className="overflow-auto" onScroll={() => handleScroll('right')}>
          {filteredLines.map((line, i) => {
            const isMoveType = line.type === 'move_out' || line.type === 'move_in';
            return (
              <div
                key={i}
                className={`px-2 py-0.5 whitespace-pre-wrap break-all min-h-[1.5em] ${
                  line.type === 'insert' ? 'bg-green-50' : line.type === 'replace' ? 'bg-yellow-50' : ''
                }`}
                style={moveLineStyle(line, 'right')}
                onMouseEnter={isMoveType ? () => setHoveredMoveId(line.moveId) : undefined}
                onMouseLeave={isMoveType ? () => setHoveredMoveId(null) : undefined}
              >
                <span className="text-gray-400 text-xs mr-2 select-none inline-block w-8 text-right">
                  {line.right_num || ''}
                </span>
                {line.right_text || ''}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
