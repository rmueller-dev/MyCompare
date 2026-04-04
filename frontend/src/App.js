import React, { useState, useEffect, useCallback } from 'react';
import DOMPurify from 'dompurify';

const API = '/api';

// Configure DOMPurify to allow safe inline styles
DOMPurify.addHook('uponSanitizeAttribute', (node, data) => {
  if (data.attrName === 'style') {
    // Only allow safe CSS properties for formatting display
    const allowed = /^(font-weight|font-style|font-size|font-family|text-decoration|text-align|color|background-color|vertical-align|margin-right|padding|border-radius):/;
    const parts = data.attrValue.split(';').filter(p => allowed.test(p.trim()));
    data.attrValue = parts.join(';');
  }
});

// ─── FILE TYPE ICONS & LABELS ───
const FILE_TYPE_META = {
  docx: { label: 'Word', color: 'bg-blue-100 text-blue-800', icon: 'W' },
  xlsx: { label: 'Excel', color: 'bg-green-100 text-green-800', icon: 'X' },
  pptx: { label: 'PowerPoint', color: 'bg-orange-100 text-orange-800', icon: 'P' },
  pdf:  { label: 'PDF', color: 'bg-red-100 text-red-800', icon: 'PDF' },
};

// ─── SAFE HTML RENDER (sanitized with DOMPurify) ───
function FormattedText({ html, fallback }) {
  if (!html) return <>{fallback || ''}</>;
  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['span', 'div', 'br', 'em', 'b', 'i', 'u', 's', 'strong', 'sub', 'sup'],
    ALLOWED_ATTR: ['style'],
  });
  return <span dangerouslySetInnerHTML={{ __html: clean }} />;
}

// ─── VERIFICATION BADGE ───
function VerificationBadge({ verification }) {
  if (!verification) return null;
  const { status, message, detail, hash_a, hash_b, change_count, delta_mismatch } = verification;

  const colors = {
    green:  'bg-green-50 border-green-400 text-green-800',
    yellow: 'bg-yellow-50 border-yellow-400 text-yellow-800',
    red:    'bg-red-50 border-red-400 text-red-900',
  };
  const icons = { green: '\u2705', yellow: '\u26A0\uFE0F', red: '\uD83D\uDD34' };

  return (
    <div className={`border-2 rounded-lg p-4 mb-4 ${colors[status] || colors.red}`}>
      <div className="flex items-center gap-2 font-bold text-lg">
        <span>{icons[status]}</span>
        <span>{message}</span>
      </div>
      <p className="mt-1 text-sm">{detail}</p>
      <div className="mt-2 text-xs font-mono opacity-70 space-y-0.5">
        <div>SHA-256 A: {hash_a?.substring(0, 16)}...</div>
        <div>SHA-256 B: {hash_b?.substring(0, 16)}...</div>
        {delta_mismatch > 0 && <div>Delta-Abweichung: {delta_mismatch} Zeichen</div>}
        <div>Erkannte Änderungen: {change_count}</div>
      </div>
    </div>
  );
}

// ─── VIEW MODE TOGGLE ───
function ViewModeToggle({ mode, setMode }) {
  return (
    <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
      {[['formatted', 'Formatiert'], ['plain', 'Nur Text']].map(([val, label]) => (
        <button key={val} onClick={() => setMode(val)}
          className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
            mode === val ? 'bg-white shadow text-gray-800' : 'text-gray-500 hover:text-gray-700'
          }`}>{label}</button>
      ))}
    </div>
  );
}

// ─── EXPORT BUTTON ───
function ExportButton({ docId, versionA, versionB }) {
  const [open, setOpen] = useState(false);

  if (!docId || !versionA || !versionB) return null;

  const doExport = (fmt) => {
    window.open(`${API}/export-changes/${docId}/${versionA}/${versionB}?format=${fmt}`, '_blank');
    setOpen(false);
  };

  return (
    <div className="relative inline-block">
      <button onClick={() => setOpen(!open)}
        className="bg-gray-100 text-gray-700 px-3 py-1.5 rounded text-sm font-medium hover:bg-gray-200 transition-colors">
        Änderungen exportieren
      </button>
      {open && (
        <div className="absolute right-0 mt-1 bg-white border rounded-lg shadow-lg z-10 py-1 w-48">
          <button onClick={() => doExport('original')}
            className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50">
            Originalformat herunterladen
          </button>
          <button onClick={() => doExport('pdf')}
            className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50">
            Als PDF herunterladen
          </button>
        </div>
      )}
    </div>
  );
}

// ─── UNIFIED DIFF VIEW ───
function DiffView({ diffResult }) {
  const [viewMode, setViewMode] = useState('formatted');

  if (!diffResult) return null;
  const { unified_lines, structural_changes, summary, verification } = diffResult;

  const formattingChanges = structural_changes?.filter(c => c.type === 'formatting') || [];
  const contentChanges = structural_changes?.filter(c => c.type !== 'formatting') || [];

  return (
    <div>
      <VerificationBadge verification={verification} />

      <div className="mb-4 flex flex-wrap items-center gap-4 text-sm text-gray-600">
        <span>Inhaltsänderungen: <b>{contentChanges.length}</b></span>
        <span>Formatierungsänderungen: <b>{summary?.formatting_count || 0}</b></span>
        <span>Plaintext-Änderungen: <b>{summary?.plaintext_count}</b></span>
        <span>Zeilen alt: <b>{summary?.total_lines_a}</b></span>
        <span>Zeilen neu: <b>{summary?.total_lines_b}</b></span>
        <div className="ml-auto flex gap-2 items-center">
          <ExportButton
            docId={diffResult.document?.id}
            versionA={diffResult.version_a?.version_number}
            versionB={diffResult.version_b?.version_number}
          />
          <ViewModeToggle mode={viewMode} setMode={setViewMode} />
        </div>
      </div>

      {/* Formatting-only changes */}
      {formattingChanges.length > 0 && (
        <div className="mb-4">
          <h3 className="font-semibold text-gray-700 mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-purple-500"></span>
            Formatierungsänderungen
          </h3>
          <div className="space-y-2">
            {formattingChanges.map((ch, i) => (
              <FormattingChange key={i} change={ch} viewMode={viewMode} />
            ))}
          </div>
        </div>
      )}

      {/* Structural content changes */}
      {contentChanges.length > 0 && (
        <div className="mb-4">
          <h3 className="font-semibold text-gray-700 mb-2">Strukturelle Änderungen</h3>
          <div className="space-y-2">
            {contentChanges.map((ch, i) => (
              <StructuralChange key={i} change={ch} viewMode={viewMode} />
            ))}
          </div>
        </div>
      )}

      {/* Side-by-side diff */}
      <h3 className="font-semibold text-gray-700 mb-2">Zeilenvergleich</h3>
      <div className="border rounded-lg overflow-hidden text-sm font-mono">
        <div className="grid grid-cols-2 bg-gray-100 border-b text-xs font-semibold text-gray-600 uppercase">
          <div className="px-3 py-1.5">Version A (alt)</div>
          <div className="px-3 py-1.5">Version B (neu)</div>
        </div>
        <div className="max-h-[60vh] overflow-auto">
          {unified_lines && unified_lines.map((line, i) => (
            <DiffLine key={i} line={line} viewMode={viewMode} />
          ))}
          {(!unified_lines || unified_lines.length === 0) && (
            <div className="p-4 text-center text-gray-400">Keine Zeilen zum Anzeigen</div>
          )}
        </div>
      </div>
    </div>
  );
}

function FormattingChange({ change, viewMode }) {
  return (
    <div className="border border-purple-200 rounded p-3 bg-purple-50">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs px-2 py-0.5 rounded font-medium bg-purple-100 text-purple-800">
          Formatierung
        </span>
        <span className="text-xs text-gray-500">{change.location}</span>
      </div>
      <div className="text-xs space-y-0.5 mb-2">
        {(change.formatting_changes || []).map((fc, i) => (
          <div key={i} className="flex items-center gap-1">
            <span className="text-purple-600">•</span>
            <span>{fc}</span>
          </div>
        ))}
      </div>
      {/* Show formatted preview if available */}
      {viewMode === 'formatted' && (change.old_items || change.old_html) && (
        <div className="flex gap-2 text-xs">
          <div className="flex-1 bg-white p-2 rounded border">
            <div className="text-[10px] text-gray-400 mb-1">Vorher:</div>
            {change.old_items ? (
              change.old_items.map((it, j) => (
                <div key={j}><FormattedText html={it.html} fallback={it.text} /></div>
              ))
            ) : (
              <FormattedText html={change.old_html} fallback={change.old_text} />
            )}
          </div>
          <div className="flex-1 bg-white p-2 rounded border">
            <div className="text-[10px] text-gray-400 mb-1">Nachher:</div>
            {change.new_items ? (
              change.new_items.map((it, j) => (
                <div key={j}><FormattedText html={it.html} fallback={it.text} /></div>
              ))
            ) : (
              <FormattedText html={change.new_html} fallback={change.new_text} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StructuralChange({ change, viewMode }) {
  const typeLabels = { replace: 'Geändert', insert: 'Eingefügt', delete: 'Gelöscht' };
  const typeColors = {
    replace: 'bg-yellow-100 text-yellow-800',
    insert: 'bg-green-100 text-green-800',
    delete: 'bg-red-100 text-red-800',
  };

  const showFormatted = viewMode === 'formatted';

  return (
    <div className="border rounded p-3 bg-white">
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs px-2 py-0.5 rounded font-medium ${typeColors[change.type]}`}>
          {typeLabels[change.type] || change.type}
        </span>
        <span className="text-xs text-gray-500">{change.location}</span>
        {change.formatting_changes && change.formatting_changes.length > 0 && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 text-purple-700">
            +Formatierung
          </span>
        )}
      </div>

      {/* Show formatting changes if any */}
      {change.formatting_changes && change.formatting_changes.length > 0 && (
        <div className="text-xs text-purple-700 mb-1 space-y-0.5">
          {change.formatting_changes.map((fc, i) => (
            <div key={i} className="flex items-center gap-1"><span>•</span><span>{fc}</span></div>
          ))}
        </div>
      )}

      {change.old_text !== undefined && (
        <div className="flex gap-2 text-xs">
          {change.old_text && (
            <div className="flex-1 bg-red-50 p-1.5 rounded">
              {showFormatted && change.old_html ? (
                <FormattedText html={change.old_html} fallback={change.old_text} />
              ) : (
                <span className="line-through">{change.old_text}</span>
              )}
            </div>
          )}
          {change.new_text && (
            <div className="flex-1 bg-green-50 p-1.5 rounded">
              {showFormatted && change.new_html ? (
                <FormattedText html={change.new_html} fallback={change.new_text} />
              ) : change.new_text}
            </div>
          )}
        </div>
      )}
      {change.inline_diffs && change.inline_diffs.map((d, i) => (
        <div key={i} className="flex gap-2 text-xs mt-1">
          <div className="flex-1 bg-red-50 p-1.5 rounded">
            {showFormatted && d.old_html ? (
              <FormattedText html={d.old_html} fallback={d.old_text} />
            ) : d.old_text}
          </div>
          <div className="flex-1 bg-green-50 p-1.5 rounded">
            {showFormatted && d.new_html ? (
              <FormattedText html={d.new_html} fallback={d.new_text} />
            ) : d.new_text}
          </div>
        </div>
      ))}
      {change.old_items && !change.inline_diffs && (
        <div className="flex gap-2 text-xs">
          <div className="flex-1 bg-red-50 p-1.5 rounded">
            {change.old_items.map((it, j) => (
              <div key={j}>
                {showFormatted && it.html ? <FormattedText html={it.html} fallback={it.text} /> : it.text}
              </div>
            ))}
          </div>
          {change.new_items && (
            <div className="flex-1 bg-green-50 p-1.5 rounded">
              {change.new_items.map((it, j) => (
                <div key={j}>
                  {showFormatted && it.html ? <FormattedText html={it.html} fallback={it.text} /> : it.text}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DiffLine({ line, viewMode }) {
  const bg = {
    equal: '',
    replace: 'bg-yellow-50',
    delete: 'bg-red-50',
    insert: 'bg-green-50',
  };

  const showFormatted = viewMode === 'formatted';

  return (
    <div className={`grid grid-cols-2 border-b border-gray-100 ${bg[line.type]}`}>
      <div className="flex">
        <span className="w-10 text-right pr-2 text-gray-400 text-xs leading-6 select-none flex-shrink-0">
          {line.left_num || ''}
        </span>
        <span className={`flex-1 px-2 py-0.5 whitespace-pre-wrap break-all ${line.type === 'delete' ? 'bg-red-100' : line.type === 'replace' ? 'bg-red-50' : ''}`}>
          {line.type === 'replace' && line.inline_diff ? (
            <InlineHighlight tokens={line.inline_diff} side="old" text={line.left_text} />
          ) : showFormatted && line.left_html ? (
            <FormattedText html={line.left_html} fallback={line.left_text} />
          ) : line.left_text}
        </span>
      </div>
      <div className="flex border-l border-gray-200">
        <span className="w-10 text-right pr-2 text-gray-400 text-xs leading-6 select-none flex-shrink-0">
          {line.right_num || ''}
        </span>
        <span className={`flex-1 px-2 py-0.5 whitespace-pre-wrap break-all ${line.type === 'insert' ? 'bg-green-100' : line.type === 'replace' ? 'bg-green-50' : ''}`}>
          {line.type === 'replace' && line.inline_diff ? (
            <InlineHighlight tokens={line.inline_diff} side="new" text={line.right_text} />
          ) : showFormatted && line.right_html ? (
            <FormattedText html={line.right_html} fallback={line.right_text} />
          ) : line.right_text}
        </span>
      </div>
    </div>
  );
}

function InlineHighlight({ tokens, side, text }) {
  if (!tokens || tokens.length === 0) return <>{text}</>;

  const parts = [];
  let i = 0;
  for (const tok of tokens) {
    const oldToks = tok.old_tokens || [];
    const newToks = tok.new_tokens || [];
    if (side === 'old') {
      for (const t of oldToks) {
        parts.push(<span key={i++} className="bg-red-300 rounded px-0.5">{t}</span>);
      }
    } else {
      for (const t of newToks) {
        parts.push(<span key={i++} className="bg-green-300 rounded px-0.5">{t}</span>);
      }
    }
  }
  return parts.length > 0 ? <>{parts}</> : <>{text}</>;
}

// ─── QUICK COMPARE (drop files → instant diff) ───
function QuickCompare({ onResult, onDocCreated, documents }) {
  const [fileOld, setFileOld] = useState(null);
  const [fileNew, setFileNew] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState(false);

  const ALLOWED = ['.docx', '.xlsx', '.pptx', '.pdf'];
  const isAllowed = (name) => ALLOWED.some(ext => name.toLowerCase().endsWith(ext));
  const getExt = (name) => name.split('.').pop().toLowerCase();

  // Prevent browser from opening dropped files (must be on window level)
  useEffect(() => {
    const prevent = (e) => { e.preventDefault(); e.stopPropagation(); };
    window.addEventListener('dragover', prevent);
    window.addEventListener('drop', prevent);
    return () => {
      window.removeEventListener('dragover', prevent);
      window.removeEventListener('drop', prevent);
    };
  }, []);

  // Find existing document that matches a filename + type
  const findExistingDoc = (filename) => {
    if (!documents || documents.length === 0) return null;
    const ext = getExt(filename);
    const baseName = filename.replace(/\.[^.]+$/, '').toLowerCase();
    // Look for a document with same type and similar name
    for (const doc of documents) {
      if (doc.file_type !== ext) continue;
      const docBase = doc.name.toLowerCase();
      // Match if names overlap or if any version has a matching filename
      if (docBase.includes(baseName) || baseName.includes(docBase)) return doc;
      for (const v of (doc.versions || [])) {
        const vBase = v.filename.replace(/\.[^.]+$/, '').toLowerCase();
        if (vBase === baseName || vBase.includes(baseName) || baseName.includes(vBase)) return doc;
      }
    }
    return null;
  };

  const handleFiles = (files) => {
    const valid = Array.from(files).filter(f => isAllowed(f.name));
    if (valid.length === 0) {
      setError('Nicht unterstützter Dateityp. Erlaubt: DOCX, XLSX, PPTX, PDF');
      return;
    }
    setError('');

    if (valid.length >= 2) {
      // Two files: sort by lastModified — older first
      valid.sort((a, b) => (a.lastModified || 0) - (b.lastModified || 0));
      setFileOld(valid[0]);
      setFileNew(valid[1]);
    } else if (valid.length === 1) {
      // One file: check if there's an existing version to compare against
      const file = valid[0];
      const existingDoc = findExistingDoc(file.name);

      if (existingDoc && existingDoc.versions && existingDoc.versions.length > 0) {
        // Auto-upload as new version and diff against latest
        autoUploadAndDiff(file, existingDoc);
      } else if (!fileOld) {
        setFileOld(file);
        setStatus('Erste Datei geladen. Jetzt die zweite Datei hinzufügen, oder einfach noch eine reinziehen.');
      } else {
        setFileNew(file);
        setStatus('');
      }
    }
  };

  // Upload single file as new version to existing doc, then auto-diff
  const autoUploadAndDiff = async (file, existingDoc) => {
    setLoading(true);
    setStatus(`Vorversion gefunden: "${existingDoc.name}" — lade als neue Version hoch und vergleiche...`);
    setError('');
    try {
      // Upload as new version
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_id', String(existingDoc.id));
      formData.append('label', 'Neue Version (automatisch)');
      const uploadRes = await fetch(`${API}/documents`, { method: 'POST', body: formData });
      const uploadData = await uploadRes.json();
      if (!uploadRes.ok) throw new Error(uploadData.error || 'Upload fehlgeschlagen');

      // Get the last two versions
      const versions = uploadData.versions || [];
      if (versions.length < 2) throw new Error('Nicht genug Versionen für Vergleich');
      const verOld = versions[versions.length - 2];
      const verNew = versions[versions.length - 1];

      // Run diff
      const diffRes = await fetch(`${API}/diff/${existingDoc.id}/${verOld.version_number}/${verNew.version_number}`);
      const diffData = await diffRes.json();
      if (!diffRes.ok) throw new Error(diffData.error || 'Vergleich fehlgeschlagen');

      onResult(diffData);
      if (onDocCreated) onDocCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setStatus('');
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  };

  const swap = () => {
    const tmp = fileOld;
    setFileOld(fileNew);
    setFileNew(tmp);
  };

  const runCompare = async () => {
    if (!fileOld || !fileNew) return;
    setLoading(true);
    setStatus('Vergleich läuft...');
    setError('');
    const formData = new FormData();
    formData.append('file_old', fileOld);
    formData.append('file_new', fileNew);
    try {
      const res = await fetch(`${API}/quick-compare`, { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Vergleich fehlgeschlagen');
      onResult(data);
      if (onDocCreated) onDocCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setStatus('');
    }
  };

  // Auto-run when both files are set
  useEffect(() => {
    if (fileOld && fileNew && !loading) {
      runCompare();
    }
  // eslint-disable-next-line
  }, [fileOld, fileNew]);

  return (
    <div className="flex flex-col items-center justify-center h-full">
      <div
        className={`w-full max-w-2xl rounded-2xl p-12 text-center transition-all cursor-pointer
          ${dragOver
            ? 'border-4 border-primary-400 bg-primary-50 scale-[1.02] shadow-lg'
            : 'border-4 border-dashed border-gray-300 bg-white hover:border-primary-300 hover:bg-gray-50'}`}
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => {
          if (!loading) document.getElementById('quick-file-input')?.click();
        }}
      >
        <input id="quick-file-input" type="file" className="hidden" multiple accept=".docx,.xlsx,.pptx,.pdf"
          onChange={e => { handleFiles(e.target.files); e.target.value = ''; }} />

        {loading ? (
          <div>
            <div className="inline-block w-12 h-12 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin mb-4"></div>
            <p className="text-lg font-medium text-gray-700">Vergleich läuft...</p>
            <p className="text-sm text-gray-500 mt-1">{status || 'Dateien werden analysiert und verifiziert'}</p>
          </div>
        ) : (
          <div>
            <svg className="w-16 h-16 mx-auto mb-4 text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5"
                d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" />
            </svg>
            <p className="text-xl font-semibold text-gray-700 mb-2">
              Dateien hierher ziehen
            </p>
            <p className="text-sm text-gray-500 mb-4">
              oder klicken zum Auswählen
            </p>
            <div className="text-xs text-gray-400 space-y-1">
              <p>2 Dateien = sofortiger Vergleich (ältere wird automatisch erkannt)</p>
              <p>1 Datei = wird automatisch mit der letzten Version verglichen</p>
              <p>DOCX, XLSX, PPTX oder PDF</p>
            </div>
          </div>
        )}
      </div>

      {/* File status */}
      {(fileOld || fileNew) && !loading && (
        <div className="mt-6 w-full max-w-2xl">
          <div className="flex items-center gap-4">
            <div className={`flex-1 rounded-lg p-3 text-sm ${fileOld ? 'bg-blue-50 border border-blue-200' : 'bg-gray-50 border border-dashed border-gray-300'}`}>
              <div className="text-xs text-gray-500 mb-1">Alte Version</div>
              {fileOld ? (
                <div className="flex items-center justify-between">
                  <span className="font-medium text-gray-800 truncate">{fileOld.name}</span>
                  <button onClick={(e) => { e.stopPropagation(); setFileOld(null); setStatus(''); }}
                    className="text-gray-400 hover:text-red-500 ml-2 text-xs">X</button>
                </div>
              ) : (
                <span className="text-gray-400">Datei auswählen...</span>
              )}
            </div>

            <button onClick={(e) => { e.stopPropagation(); swap(); }}
              className="text-gray-400 hover:text-primary-600 p-2 flex-shrink-0" title="Reihenfolge tauschen">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
            </button>

            <div className={`flex-1 rounded-lg p-3 text-sm ${fileNew ? 'bg-green-50 border border-green-200' : 'bg-gray-50 border border-dashed border-gray-300'}`}>
              <div className="text-xs text-gray-500 mb-1">Neue Version</div>
              {fileNew ? (
                <div className="flex items-center justify-between">
                  <span className="font-medium text-gray-800 truncate">{fileNew.name}</span>
                  <button onClick={(e) => { e.stopPropagation(); setFileNew(null); setStatus(''); }}
                    className="text-gray-400 hover:text-red-500 ml-2 text-xs">X</button>
                </div>
              ) : (
                <span className="text-gray-400">Zweite Datei hinzufügen...</span>
              )}
            </div>
          </div>
        </div>
      )}

      {status && !loading && (
        <div className="mt-4 w-full max-w-2xl text-sm text-blue-700 bg-blue-50 border border-blue-200 p-3 rounded-lg">
          {status}
        </div>
      )}

      {error && (
        <div className="mt-4 w-full max-w-2xl text-sm text-red-600 bg-red-50 border border-red-200 p-3 rounded-lg">
          {error}
        </div>
      )}
    </div>
  );
}

// ─── UPLOAD MODAL ───
function UploadModal({ onClose, onUpload, documents }) {
  const [mode, setMode] = useState('new');
  const [selectedDoc, setSelectedDoc] = useState('');
  const [name, setName] = useState('');
  const [label, setLabel] = useState('');
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) { setError('Bitte Datei auswählen'); return; }
    setUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('label', label);
    if (mode === 'existing' && selectedDoc) {
      formData.append('document_id', selectedDoc);
    } else {
      formData.append('name', name || file.name.replace(/\.[^.]+$/, ''));
    }

    try {
      const res = await fetch(`${API}/documents`, { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Upload fehlgeschlagen');
      onUpload(data);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <h2 className="text-xl font-bold mb-4">Datei hochladen</h2>
        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <div className="flex gap-2 mb-3">
              <button type="button" onClick={() => setMode('new')}
                className={`px-3 py-1.5 rounded text-sm font-medium ${mode === 'new' ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-600'}`}>
                Neues Dokument
              </button>
              <button type="button" onClick={() => setMode('existing')}
                className={`px-3 py-1.5 rounded text-sm font-medium ${mode === 'existing' ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-600'}`}>
                Neue Version
              </button>
            </div>

            {mode === 'new' ? (
              <input type="text" placeholder="Dokumentname (optional)" value={name} onChange={e => setName(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm" />
            ) : (
              <select value={selectedDoc} onChange={e => setSelectedDoc(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm">
                <option value="">Dokument wählen...</option>
                {documents.map(d => (
                  <option key={d.id} value={d.id}>{d.name} ({d.file_type.toUpperCase()})</option>
                ))}
              </select>
            )}
          </div>

          <div className="mb-4">
            <input type="text" placeholder="Versions-Notiz (optional)" value={label} onChange={e => setLabel(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm" />
          </div>

          <div className="mb-4">
            <label className="block border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-primary-400 transition-colors">
              <input type="file" className="hidden" accept=".docx,.xlsx,.pptx,.pdf"
                onChange={e => setFile(e.target.files[0])} />
              {file ? (
                <span className="text-sm font-medium text-primary-700">{file.name}</span>
              ) : (
                <span className="text-sm text-gray-500">DOCX, XLSX, PPTX oder PDF hierher ziehen oder klicken</span>
              )}
            </label>
          </div>

          {error && <div className="mb-3 text-sm text-red-600 bg-red-50 p-2 rounded">{error}</div>}

          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">
              Abbrechen
            </button>
            <button type="submit" disabled={uploading}
              className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
              {uploading ? 'Wird hochgeladen...' : 'Hochladen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── MAIN APP ───
export default function App() {
  const [documents, setDocuments] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [diffResult, setDiffResult] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [versionA, setVersionA] = useState(null);
  const [versionB, setVersionB] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [quickDiff, setQuickDiff] = useState(null);

  const loadDocuments = useCallback(async () => {
    try {
      const res = await fetch(`${API}/documents`);
      const data = await res.json();
      setDocuments(data);
    } catch (err) {
      console.error('Failed to load documents:', err);
    }
  }, []);

  useEffect(() => { loadDocuments(); }, [loadDocuments]);

  const selectDocument = (doc) => {
    setSelectedDoc(doc);
    setDiffResult(null);
    setVersionA(null);
    setVersionB(null);
  };

  const handleUpload = (doc) => {
    loadDocuments();
    setSelectedDoc(doc);
  };

  const runDiff = async () => {
    if (!selectedDoc || !versionA || !versionB) return;
    setDiffLoading(true);
    setDiffResult(null);
    try {
      const res = await fetch(`${API}/diff/${selectedDoc.id}/${versionA}/${versionB}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      setDiffResult(data);
    } catch (err) {
      alert('Diff-Fehler: ' + err.message);
    } finally {
      setDiffLoading(false);
    }
  };

  const deleteDocument = async (docId) => {
    if (!window.confirm('Dokument wirklich löschen? Die gespeicherten Dateien bleiben erhalten.')) return;
    await fetch(`${API}/documents/${docId}`, { method: 'DELETE' });
    setSelectedDoc(null);
    setDiffResult(null);
    loadDocuments();
  };

  // Group documents by type
  const grouped = {};
  for (const d of documents) {
    const t = d.file_type || 'other';
    if (!grouped[t]) grouped[t] = [];
    grouped[t].push(d);
  }

  const versions = selectedDoc?.versions || [];

  return (
    <div className="h-screen flex flex-col">
      {/* TOP BAR */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between flex-shrink-0 shadow-sm">
        <div className="flex items-center gap-3">
          <button onClick={() => setSidebarOpen(!sidebarOpen)} className="text-gray-500 hover:text-gray-700 lg:hidden">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <h1 className="text-xl font-bold text-gray-800">MyCompare</h1>
          {selectedDoc && (
            <span className="text-sm text-gray-500 hidden sm:inline">
              &mdash; {selectedDoc.name}
              <span className={`ml-2 text-xs px-1.5 py-0.5 rounded font-medium ${FILE_TYPE_META[selectedDoc.file_type]?.color}`}>
                {selectedDoc.file_type?.toUpperCase()}
              </span>
            </span>
          )}
        </div>
        <button onClick={() => setShowUpload(true)}
          className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary-700 transition-colors shadow-sm">
          + Hochladen
        </button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* LEFT SIDEBAR */}
        <aside className={`${sidebarOpen ? 'w-72' : 'w-0 overflow-hidden'} bg-white border-r border-gray-200 flex-shrink-0 transition-all duration-200 flex flex-col`}>
          <div className="p-3 border-b border-gray-100">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Dokumentenbibliothek</h2>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {documents.length === 0 && (
              <div className="text-center text-gray-400 text-sm py-8">
                Keine Dokumente.<br />Laden Sie eine Datei hoch.
              </div>
            )}
            {['docx', 'xlsx', 'pptx', 'pdf'].map(type => {
              const docs = grouped[type];
              if (!docs || docs.length === 0) return null;
              const meta = FILE_TYPE_META[type];
              return (
                <div key={type} className="mb-3">
                  <div className="text-xs font-semibold text-gray-400 uppercase px-2 py-1">{meta.label}</div>
                  {docs.map(doc => (
                    <button key={doc.id} onClick={() => selectDocument(doc)}
                      className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                        selectedDoc?.id === doc.id ? 'bg-primary-50 text-primary-800 font-medium' : 'hover:bg-gray-50 text-gray-700'
                      }`}>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs w-6 h-6 rounded flex items-center justify-center font-bold ${meta.color}`}>
                          {meta.icon}
                        </span>
                        <span className="truncate">{doc.name}</span>
                        <span className="text-xs text-gray-400 ml-auto">{doc.versions?.length || 0}v</span>
                      </div>
                    </button>
                  ))}
                </div>
              );
            })}
          </div>
        </aside>

        {/* MAIN AREA */}
        <main className="flex-1 overflow-y-auto p-6">
          {quickDiff && !selectedDoc ? (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-2xl font-bold text-gray-800">Schnellvergleich</h2>
                <button onClick={() => setQuickDiff(null)}
                  className="text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 px-3 py-1.5 rounded">
                  Neuer Vergleich
                </button>
              </div>
              <DiffView diffResult={quickDiff} />
            </div>
          ) : !selectedDoc ? (
            <QuickCompare
              onResult={(data) => { setQuickDiff(data); }}
              onDocCreated={loadDocuments}
              documents={documents}
            />
          ) : (
            <div>
              {/* Document header */}
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h2 className="text-2xl font-bold text-gray-800">{selectedDoc.name}</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    {versions.length} Version{versions.length !== 1 ? 'en' : ''} &middot;
                    Erstellt: {selectedDoc.created_at ? new Date(selectedDoc.created_at).toLocaleDateString('de-DE') : '—'}
                  </p>
                </div>
                <button onClick={() => deleteDocument(selectedDoc.id)}
                  className="text-sm text-red-500 hover:text-red-700 hover:bg-red-50 px-3 py-1.5 rounded">
                  Löschen
                </button>
              </div>

              {/* Version timeline */}
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wider mb-3">Versionen</h3>
                <div className="space-y-2">
                  {versions.map(v => (
                    <div key={v.id} className="flex items-center gap-3 bg-white border rounded-lg p-3">
                      <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center font-bold text-sm">
                        {v.version_number}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-800 truncate">{v.filename}</div>
                        <div className="text-xs text-gray-500">
                          {v.uploaded_at ? new Date(v.uploaded_at).toLocaleString('de-DE') : ''}
                          {v.label && <span className="ml-2 italic">{v.label}</span>}
                        </div>
                      </div>
                      <a href={`${API}/download/${selectedDoc.id}/${v.id}`}
                        className="text-xs text-primary-600 hover:underline">Download</a>
                    </div>
                  ))}
                </div>
              </div>

              {/* Diff selector */}
              {versions.length >= 2 && (
                <div className="mb-6 bg-white border rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wider mb-3">Vergleich</h3>
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <label className="text-sm text-gray-600">Version A:</label>
                      <select value={versionA || ''} onChange={e => setVersionA(Number(e.target.value))}
                        className="border rounded px-2 py-1 text-sm">
                        <option value="">Wählen...</option>
                        {versions.map(v => (
                          <option key={v.id} value={v.version_number}>
                            V{v.version_number} — {v.filename}
                          </option>
                        ))}
                      </select>
                    </div>
                    <span className="text-gray-400 font-bold">vs.</span>
                    <div className="flex items-center gap-2">
                      <label className="text-sm text-gray-600">Version B:</label>
                      <select value={versionB || ''} onChange={e => setVersionB(Number(e.target.value))}
                        className="border rounded px-2 py-1 text-sm">
                        <option value="">Wählen...</option>
                        {versions.map(v => (
                          <option key={v.id} value={v.version_number}>
                            V{v.version_number} — {v.filename}
                          </option>
                        ))}
                      </select>
                    </div>
                    <button onClick={runDiff} disabled={!versionA || !versionB || versionA === versionB || diffLoading}
                      className="bg-primary-600 text-white px-4 py-1.5 rounded text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors">
                      {diffLoading ? 'Vergleiche...' : 'Vergleichen'}
                    </button>
                  </div>
                  {versionA && versionB && versionA === versionB && (
                    <p className="text-xs text-yellow-600 mt-2">Bitte zwei unterschiedliche Versionen wählen.</p>
                  )}
                </div>
              )}
              {versions.length < 2 && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-sm text-yellow-800">
                  Laden Sie mindestens zwei Versionen hoch, um einen Vergleich durchzuführen.
                </div>
              )}

              {/* Diff result */}
              {diffLoading && (
                <div className="text-center py-12">
                  <div className="inline-block w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin"></div>
                  <p className="text-sm text-gray-500 mt-3">Vergleich wird durchgeführt...</p>
                </div>
              )}
              {diffResult && <DiffView diffResult={diffResult} />}
            </div>
          )}
        </main>
      </div>

      {/* Upload modal */}
      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onUpload={handleUpload}
          documents={documents}
        />
      )}
    </div>
  );
}
