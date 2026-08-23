const vscode = acquireVsCodeApi();
const host = document.getElementById('stage-host');
const titleEl = document.getElementById('title');
const rowsEl = document.getElementById('rows');
const scrubHost = document.getElementById('scrub-host');
const rowsPlaceholder = document.getElementById('rowsPlaceholder');

/** @type {HTMLImageElement | null} */
let stillImg = document.getElementById('stage-still');
/** @type {HTMLElement | null} */
let stagePlaceholder = document.getElementById('stagePlaceholder');
/** @type {HTMLElement | null} */
let stageFrame = document.getElementById('stage-frame');

function setStatus(stageText, timelineText) {
  if (stageText != null && host) {
    ensureStageDom();
    if (stillImg && stillImg.getAttribute('src')) {
      // Keep showing the last still; only update chrome / pending state elsewhere.
    } else if (stagePlaceholder) {
      stagePlaceholder.hidden = false;
      stagePlaceholder.textContent = String(stageText);
    }
  }
  if (timelineText != null && rowsEl) {
    if (!rowsEl.querySelector('.row') && !rowsEl.querySelector('.section-group')) {
      rowsEl.textContent = '';
      const p = document.createElement('div');
      p.className = 'placeholder';
      p.id = 'rowsPlaceholder';
      p.textContent = String(timelineText);
      rowsEl.appendChild(p);
    } else if (rowsPlaceholder) {
      rowsPlaceholder.textContent = String(timelineText);
    }
  }
}

setStatus('Webview script running…', 'Webview script running…');

let timeline = null;
let pendingHighlightLine = null;
let pendingHighlightTime = null;
let scrubTime = 0;
let scrubUntilLine = null;
/** @type {string | null} */
let stillUri = null;
let snapshotPending = false;
let snapshotError = null;
let scrubEl = null;
let scrubLabel = null;
let reorderArmed = false;
let selectedAfterLine = null;
let pendingPayload = null;

function ensureStageDom() {
  if (!host) return;
  if (!stageFrame || !host.contains(stageFrame)) {
    host.textContent = '';
    stageFrame = document.createElement('div');
    stageFrame.id = 'stage-frame';
    stillImg = document.createElement('img');
    stillImg.id = 'stage-still';
    stillImg.alt = 'Manim still';
    stillImg.hidden = true;
    stillImg.draggable = false;
    stagePlaceholder = document.createElement('div');
    stagePlaceholder.className = 'placeholder';
    stagePlaceholder.id = 'stagePlaceholder';
    stageFrame.appendChild(stillImg);
    stageFrame.appendChild(stagePlaceholder);
    host.appendChild(stageFrame);
    stageFrame.addEventListener('click', () => {
      if (scrubUntilLine != null) {
        vscode.postMessage({ type: 'jumpScrubLine', line: scrubUntilLine });
      }
    });
  }
}

function fmt(n) {
  return (Math.round(n * 100) / 100).toString();
}

function isBeat(ev) {
  return ev.kind === 'play' || ev.kind === 'wait';
}

function eventSection(ev) {
  return (ev && ev.section != null) ? String(ev.section) : '';
}

function sectionGroups() {
  return Array.from(rowsEl.querySelectorAll(':scope > .section-group'));
}

function updateChromeTitle() {
  const scene = (timeline && timeline.scene) || '';
  const total = timeline ? fmt(timeline.total_duration || 0) + 's' : '';
  let text = 'Stage & Timeline: ' + scene;
  if (total) text += ' · ' + total;
  if (scrubTime != null && timeline) {
    text += ' · scrub t=' + fmt(scrubTime) + 's';
  }
  if (snapshotPending) {
    text += stillUri ? ' · Capturing…' : ' · Capturing still…';
  } else if (stillUri) {
    text += ' · Manim still';
  } else if (snapshotError) {
    text += ' · Still failed';
  }
  titleEl.textContent = text;
}

function stagePlaceholderText() {
  if (snapshotPending && !stillUri) return 'Capturing Manim still…';
  if (snapshotError && !stillUri) return 'Still failed: ' + snapshotError;
  if (!timeline) return 'Waiting for timeline…';
  if (!stillUri) return 'Scrub to capture a Manim still';
  return '';
}

function syncStageVisual() {
  ensureStageDom();
  if (!stillImg || !stagePlaceholder) return;

  if (stillUri) {
    if (stillImg.getAttribute('src') !== stillUri) {
      stillImg.src = stillUri;
    }
    stillImg.hidden = false;
    stillImg.classList.toggle('pending', !!snapshotPending);
    const tip = stagePlaceholderText();
    if (tip && snapshotPending) {
      // Keep last frame; no blocking placeholder.
      stagePlaceholder.hidden = true;
    } else {
      stagePlaceholder.hidden = true;
    }
  } else {
    stillImg.removeAttribute('src');
    stillImg.hidden = true;
    stillImg.classList.remove('pending');
    stagePlaceholder.hidden = false;
    stagePlaceholder.textContent = stagePlaceholderText();
  }
  updateChromeTitle();
}

function clearStill(keepPendingHint) {
  stillUri = null;
  if (stillImg) {
    stillImg.removeAttribute('src');
    stillImg.hidden = true;
    stillImg.classList.remove('pending');
  }
  if (!keepPendingHint) {
    snapshotError = null;
  }
  syncStageVisual();
}

function bindBeatSortable(row, opts) {
  row.classList.add('sortable');
  const grip = row.querySelector('.label') || row;
  let startY = 0;
  let fromPos = opts.pos;
  let active = false;
  let moved = false;

  const peerRows = () => {
    const group = row.closest('.section-group') || rowsEl;
    return Array.from(group.querySelectorAll('.row')).filter((el) => {
      return el.dataset.sortKind === 'beat' && el.dataset.section === opts.section;
    });
  };

  const onPointerMove = (e) => {
    if (!active) return;
    const dy = e.clientY - startY;
    if (!moved && Math.abs(dy) < 4) return;
    moved = true;
    reorderArmed = true;
    row.classList.add('sortable-dragging');
    row.style.transform = 'translateY(' + dy + 'px)';
    const peers = peerRows();
    const idx = peers.indexOf(row);
    if (idx < 0) return;
    const rect = row.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;
    const parent = row.parentElement;
    for (let i = 0; i < peers.length; i++) {
      const other = peers[i];
      if (other === row) continue;
      const or = other.getBoundingClientRect();
      const oMid = or.top + or.height / 2;
      if (midY < oMid && i < idx) {
        parent.insertBefore(row, other);
        startY = e.clientY;
        row.style.transform = '';
        break;
      }
      if (midY > oMid && i > idx) {
        parent.insertBefore(other, row);
        startY = e.clientY;
        row.style.transform = '';
        break;
      }
    }
  };

  const endPointer = (e) => {
    if (!active) return;
    active = false;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', endPointer);
    window.removeEventListener('pointercancel', endPointer);
    row.classList.remove('sortable-dragging');
    row.style.transform = '';
    try { row.releasePointerCapture(e.pointerId); } catch (_) {}
    if (!moved) {
      reorderArmed = false;
      return;
    }
    const peers = peerRows();
    const toPos = peers.indexOf(row);
    const list = opts.list;
    if (toPos < 0 || toPos === fromPos || !list[fromPos] || !list[toPos]) {
      reorderArmed = false;
      rebuildTimeline();
      return;
    }
    vscode.postMessage({
      type: 'reorder',
      kind: 'beat',
      lineA: list[fromPos].range && list[fromPos].range.start_line,
      lineB: list[toPos].range && list[toPos].range.start_line
    });
    setTimeout(() => { reorderArmed = false; }, 0);
  };

  grip.addEventListener('pointerdown', (e) => {
    if (e.button != null && e.button !== 0) return;
    if (e.target && e.target.closest && e.target.closest('.handle')) return;
    e.stopPropagation();
    active = true;
    moved = false;
    fromPos = opts.pos;
    startY = e.clientY;
    try { row.setPointerCapture(e.pointerId); } catch (_) {}
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', endPointer);
    window.addEventListener('pointercancel', endPointer);
  });
}

function bindSectionGroupSortable(group, opts) {
  group.classList.add('sortable');
  const grip = group.querySelector('.section-row .label') || group;
  let startY = 0;
  let fromPos = opts.pos;
  let active = false;
  let moved = false;

  const onPointerMove = (e) => {
    if (!active) return;
    const dy = e.clientY - startY;
    if (!moved && Math.abs(dy) < 4) return;
    moved = true;
    reorderArmed = true;
    group.classList.add('sortable-dragging');
    group.style.transform = 'translateY(' + dy + 'px)';

    const peers = sectionGroups();
    const idx = peers.indexOf(group);
    if (idx < 0) return;
    const prev = peers[idx - 1];
    const next = peers[idx + 1];
    const midY = group.getBoundingClientRect().top + group.getBoundingClientRect().height / 2;
    if (prev) {
      const pr = prev.getBoundingClientRect();
      if (midY < pr.top + pr.height / 2) {
        rowsEl.insertBefore(group, prev);
        startY = e.clientY;
        group.style.transform = '';
        return;
      }
    }
    if (next) {
      const nr = next.getBoundingClientRect();
      if (midY > nr.top + nr.height / 2) {
        rowsEl.insertBefore(next, group);
        startY = e.clientY;
        group.style.transform = '';
      }
    }
  };

  const endPointer = (e) => {
    if (!active) return;
    active = false;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', endPointer);
    window.removeEventListener('pointercancel', endPointer);
    group.classList.remove('sortable-dragging');
    group.style.transform = '';
    try { group.releasePointerCapture(e.pointerId); } catch (_) {}
    if (!moved) {
      reorderArmed = false;
      return;
    }
    const peers = sectionGroups();
    const toPos = peers.indexOf(group);
    const list = opts.list;
    if (toPos < 0 || toPos === fromPos || Math.abs(toPos - fromPos) !== 1
        || !list[fromPos] || !list[toPos]) {
      reorderArmed = false;
      rebuildTimeline();
      return;
    }
    vscode.postMessage({
      type: 'reorder',
      kind: 'section',
      lineA: list[fromPos].range && list[fromPos].range.start_line,
      lineB: list[toPos].range && list[toPos].range.start_line
    });
    setTimeout(() => { reorderArmed = false; }, 0);
  };

  grip.addEventListener('pointerdown', (e) => {
    if (e.button != null && e.button !== 0) return;
    if (e.target && e.target.closest && e.target.closest('.handle')) return;
    if (e.target && e.target.closest && e.target.closest('.row.beat')) return;
    active = true;
    moved = false;
    fromPos = opts.pos;
    startY = e.clientY;
    try { group.setPointerCapture(e.pointerId); } catch (_) {}
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', endPointer);
    window.addEventListener('pointercancel', endPointer);
  });
}

function rebuildTimeline() {
  rowsEl.innerHTML = '';
  if (scrubHost) scrubHost.innerHTML = '';
  if (!timeline) {
    rowsEl.innerHTML = '<div class="placeholder">No timeline loaded.</div>';
    return;
  }
  const events = timeline.events || [];
  const total = Math.max(timeline.total_duration || 1, 0.01);
  updateChromeTitle();

  if (!events.length) {
    rowsEl.innerHTML = '<div class="placeholder">No play/wait events in this scene.</div>';
  }

  const scrubRow = document.createElement('div');
  scrubRow.className = 'scrub-row';
  const scrubGutter = document.createElement('div');
  scrubGutter.className = 'scrub-gutter';
  scrubGutter.textContent = 'Scrub';
  const scrubTrack = document.createElement('div');
  scrubTrack.className = 'scrub-track';
  const scrubInput = document.createElement('input');
  scrubInput.id = 'scrub';
  scrubInput.type = 'range';
  scrubInput.min = '0';
  scrubInput.max = '1';
  scrubInput.step = '0.01';
  scrubInput.value = '0';
  scrubTrack.appendChild(scrubInput);
  const scrubLabelEl = document.createElement('div');
  scrubLabelEl.id = 'scrubLabel';
  scrubLabelEl.textContent = '0s';
  scrubRow.appendChild(scrubGutter);
  scrubRow.appendChild(scrubTrack);
  scrubRow.appendChild(scrubLabelEl);
  if (scrubHost) {
    scrubHost.appendChild(scrubRow);
  } else {
    rowsEl.appendChild(scrubRow);
  }
  scrubEl = scrubInput;
  scrubLabel = scrubLabelEl;
  if (!scrubEl || !scrubLabel) return;
  scrubEl.max = String(total);
  scrubEl.step = String(Math.max(0.01, total / 200));
  const t0 = Math.max(0, Math.min(total, scrubTime || 0));
  scrubEl.value = String(t0);
  scrubLabel.textContent = fmt(t0) + 's';
  scrubEl.addEventListener('input', () => {
    const time = Number(scrubEl.value) || 0;
    scrubTime = time;
    scrubLabel.textContent = fmt(time) + 's';
    highlightTime(time);
    vscode.postMessage({ type: 'scrub', time: time });
  });
  vscode.postMessage({ type: 'scrub', time: t0 });

  if (!events.length) {
    return;
  }
  const groups = [];
  let cur = { section: '', sectionEv: null, beats: [] };
  events.forEach((ev, i) => {
    if (ev.kind === 'next_section') {
      if (cur.sectionEv || cur.beats.length) groups.push(cur);
      cur = { section: eventSection(ev) || String(ev.label || ''), sectionEv: ev, beats: [] };
    } else if (isBeat(ev)) {
      cur.beats.push({ ev: ev, index: i });
    }
  });
  if (cur.sectionEv || cur.beats.length) groups.push(cur);

  const sectionMarkers = groups
    .filter((g) => g.sectionEv)
    .map((g) => g.sectionEv);

  function buildRow(ev, eventIndex) {
    const row = document.createElement('div');
    row.className = 'row' + (ev.kind === 'next_section' ? ' section-row' : '') +
      (isBeat(ev) ? ' beat' : '');
    row.dataset.startLine = String(ev.range && ev.range.start_line || 0);
    row.dataset.endLine = String(ev.range && ev.range.end_line || 0);
    row.dataset.method = ev.method || '';
    row.dataset.eventIndex = String(eventIndex);
    row.dataset.eventId = String(ev.id || eventIndex);
    row.dataset.kind = ev.kind || '';
    row.dataset.section = eventSection(ev);
    row.dataset.start = String(ev.start || 0);
    row.dataset.duration = String(ev.duration || 0);
    row.dataset.targets = JSON.stringify(ev.targets || []);

    const label = document.createElement('div');
    label.className = 'label';
    const dragHint = isBeat(ev)
      ? ' · drag to reorder within this section'
      : (ev.kind === 'next_section'
        ? ' · drag this section group to swap with a neighbor'
        : '');
    const targetHint = (ev.targets && ev.targets.length)
      ? ' targets: ' + ev.targets.join(', ')
      : '';
    label.title = (ev.note || '') + (ev.method ? ' @ ' + ev.method : '') + targetHint + dragHint;
    label.textContent = ev.kind === 'next_section' ? ('§ ' + ev.label) : ev.label;
    label.addEventListener('click', (e) => {
      e.stopPropagation();
      if (reorderArmed) return;
      const line = ev.range && ev.range.start_line;
      if (line) {
        selectedAfterLine = line;
        setActiveRow(row);
      }
      vscode.postMessage({
        type: 'selectBeat',
        range: ev.range,
        kind: ev.kind,
        line: line,
        duration: ev.duration || 0,
        targets: ev.targets || []
      });
    });
    row.addEventListener('click', (e) => {
      if (reorderArmed) return;
      if (e.target && e.target.closest && e.target.closest('.handle')) return;
      const line = ev.range && ev.range.start_line;
      if (line) {
        selectedAfterLine = line;
        setActiveRow(row);
      }
      vscode.postMessage({
        type: 'selectBeat',
        range: ev.range,
        kind: ev.kind,
        line: line,
        duration: ev.duration || 0,
        targets: ev.targets || []
      });
    });

    const track = document.createElement('div');
    track.className = 'track';
    const leftPct = Math.max(0, Math.min(100, ((ev.start || 0) / total) * 100));
    const widthPct = ev.kind === 'next_section'
      ? 0
      : Math.max(0.5, Math.min(100 - leftPct, ((ev.duration || 0) / total) * 100));
    const block = document.createElement('div');
    block.className = 'block ' + ev.kind + (ev.editable ? '' : ' locked');
    block.style.left = leftPct + '%';
    block.style.width = widthPct + '%';
    track.appendChild(block);

    const dur = document.createElement('div');
    dur.className = 'dur';
    if (ev.kind === 'next_section') {
      dur.textContent = '';
    } else {
      dur.textContent = fmt(ev.duration || 0) + 's';
      if (!ev.editable) dur.title = ev.note || 'not editable';
    }

    if (ev.editable && (ev.kind === 'play' || ev.kind === 'wait')) {
      const handle = document.createElement('div');
      handle.className = 'handle';
      block.appendChild(handle);
      let startX = 0;
      let startPct = 0;
      handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        startX = e.clientX;
        startPct = widthPct;
        const trackW = Math.max(1, track.getBoundingClientRect().width);
        const onMove = (ev2) => {
          const deltaPct = ((ev2.clientX - startX) / trackW) * 100;
          const next = Math.max(0.5, Math.min(100 - leftPct, startPct + deltaPct));
          block.style.width = next + '%';
          dur.textContent = fmt((next / 100) * total) + 's';
        };
        const onUp = (ev2) => {
          window.removeEventListener('mousemove', onMove);
          window.removeEventListener('mouseup', onUp);
          const deltaPct = ((ev2.clientX - startX) / trackW) * 100;
          const next = Math.max(0.5, Math.min(100 - leftPct, startPct + deltaPct));
          const rounded = Math.round(((next / 100) * total) * 100) / 100;
          if (Math.abs(rounded - (ev.duration || 0)) < 0.01) {
            rebuildTimeline();
            return;
          }
          vscode.postMessage({
            type: 'resize',
            kind: ev.kind,
            line: ev.range && ev.range.start_line,
            duration: rounded,
            id: ev.id
          });
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
      });
    }

    row.appendChild(label);
    row.appendChild(track);
    row.appendChild(dur);
    return row;
  }

  groups.forEach((g) => {
    const groupEl = document.createElement('div');
    groupEl.className = 'section-group';
    groupEl.dataset.section = g.section;

    if (g.sectionEv) {
      const secIdx = events.indexOf(g.sectionEv);
      const secRow = buildRow(g.sectionEv, secIdx >= 0 ? secIdx : 0);
      secRow.dataset.sortKind = 'section';
      groupEl.appendChild(secRow);
      const pos = sectionMarkers.indexOf(g.sectionEv);
      if (pos >= 0) {
        bindSectionGroupSortable(groupEl, {
          pos: pos,
          list: sectionMarkers
        });
      }
    }

    const beatList = g.beats.map((b) => b.ev);
    g.beats.forEach((b, beatPos) => {
      const beatRow = buildRow(b.ev, b.index);
      beatRow.dataset.sortKind = 'beat';
      bindBeatSortable(beatRow, {
        pos: beatPos,
        section: eventSection(b.ev),
        list: beatList
      });
      groupEl.appendChild(beatRow);
    });

    rowsEl.appendChild(groupEl);
  });
  if (pendingHighlightTime != null) {
    highlightTime(pendingHighlightTime);
  } else if (pendingHighlightLine != null) {
    highlightTimelineLine(pendingHighlightLine);
  }
}

function clearActive() {
  rowsEl.querySelectorAll('.row.active').forEach((row) => {
    row.classList.remove('active');
  });
}

function setActiveRow(row) {
  clearActive();
  if (!row) return;
  row.classList.add('active');
  row.scrollIntoView({ block: 'nearest' });
  const start = Number(row.dataset.startLine || 0);
  if (start) {
    selectedAfterLine = start;
  }
}

function highlightTimelineLine(line) {
  pendingHighlightLine = line;
  pendingHighlightTime = null;
  const rows = Array.from(rowsEl.querySelectorAll('.row'));
  let best = null;
  let bestScore = Infinity;
  rows.forEach((row) => {
    const start = Number(row.dataset.startLine || 0);
    const end = Number(row.dataset.endLine || start);
    const kind = row.dataset.kind || '';
    if (!start && !end) return;
    let dist;
    if (line >= start && line <= end) {
      dist = 0;
    } else {
      dist = Math.min(Math.abs(line - start), Math.abs(line - end));
      if (dist > 3) return;
    }
    const kindPenalty = (kind === 'play' || kind === 'wait') ? 0 : 0.4;
    const score = dist + kindPenalty;
    if (score < bestScore) {
      best = row;
      bestScore = score;
    }
  });
  setActiveRow(best);
}

function highlightTime(time) {
  pendingHighlightTime = time;
  const rows = Array.from(rowsEl.querySelectorAll('.row'));
  let covering = null;
  let lastStarted = null;
  rows.forEach((row) => {
    const kind = row.dataset.kind || '';
    if (kind === 'next_section') return;
    const start = Number(row.dataset.start || 0);
    const dur = Number(row.dataset.duration || 0);
    const end = start + dur;
    if (time >= start && time <= end + 1e-9) covering = row;
    if (time >= start) lastStarted = row;
  });
  setActiveRow(covering || lastStarted);
}

function applyPayload(msg) {
  pendingPayload = msg;
  try {
    if (msg.timeline) {
      timeline = msg.timeline;
      rebuildTimeline();
    }
  } catch (err) {
    console.error('Manim Dock Timeline rebuild failed', err);
    rowsEl.innerHTML = '<div class="placeholder">Timeline failed: ' + String(err) + '</div>';
  }
  // New timeline/source → drop still; scrub will capture again.
  snapshotPending = false;
  snapshotError = null;
  clearStill(false);
  ensureStageDom();
  updateChromeTitle();
}

window.addEventListener('message', (event) => {
  const msg = event.data;
  if (!msg) return;
  if (msg.type === 'status') {
    setStatus(msg.stage, msg.timeline);
  } else if (msg.type === 'payload') {
    applyPayload(msg);
  } else if (msg.type === 'highlightLine') {
    highlightTimelineLine(msg.line);
  } else if (msg.type === 'scrub') {
    scrubTime = typeof msg.time === 'number' ? msg.time : scrubTime;
    scrubUntilLine = typeof msg.activeUntilLine === 'number' ? msg.activeUntilLine : null;
    if (scrubEl && typeof msg.time === 'number') {
      scrubEl.value = String(msg.time);
      if (scrubLabel) scrubLabel.textContent = fmt(msg.time) + 's';
    }
    // Keep last still while a new capture is in flight (dimmed via pending).
    highlightTime(scrubTime);
    updateChromeTitle();
  } else if (msg.type === 'snapshot') {
    if (msg.pending) {
      snapshotPending = true;
      snapshotError = null;
      syncStageVisual();
      return;
    }
    if (msg.ok && msg.imageUri) {
      snapshotPending = false;
      snapshotError = null;
      stillUri = String(msg.imageUri);
      syncStageVisual();
      return;
    }
    // Failure: keep previous still if any; only show placeholder when none.
    snapshotPending = false;
    snapshotError = msg.error ? String(msg.error) : 'still failed';
    syncStageVisual();
  }
});
ensureStageDom();
setStatus('Waiting for sidecar data…', 'Waiting for sidecar data…');
vscode.postMessage({ type: 'ready' });
