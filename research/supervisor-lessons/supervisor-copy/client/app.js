import { h, render } from 'https://esm.sh/preact@10.19.6';
import { useState, useEffect, useRef, useCallback } from 'https://esm.sh/preact@10.19.6/hooks';
import htm from 'https://esm.sh/htm@3.1.1';
import { getRenderer } from './panels/registry.js';

const html = htm.bind(h);

// ── Default connection config ──

const DEFAULT_CONNECTIONS = [
    { app: 'subsequence', label: 'subsequence', url: 'ws://localhost:8765', enabled: true },
    { app: 'subsample', label: 'subsample', url: 'ws://localhost:9003', enabled: true },
    { app: 'substation', label: 'substation', url: 'ws://localhost:9004', enabled: true },
];

const APP_COLORS = {
    subsequence: 'var(--color-app-subsequence)',
    subsample: 'var(--color-app-subsample)',
    substation: 'var(--color-app-substation)',
};

// ── Persistence helpers ──

function loadConnections() {
    try {
        const saved = localStorage.getItem('supervisor-connections');
        if (saved) {
            const parsed = JSON.parse(saved);
            // Merge saved url/enabled with default labels.
            const defaults = Object.fromEntries(DEFAULT_CONNECTIONS.map(c => [c.app, c]));
            return parsed.map(s => ({ ...defaults[s.app], ...s }));
        }
    } catch {}
    return DEFAULT_CONNECTIONS.map(c => ({ ...c }));
}

function saveConnections(conns) {
    // Only persist url and enabled — labels come from manifests/defaults.
    const toSave = conns.map(({ app, url, enabled }) => ({ app, url, enabled }));
    localStorage.setItem('supervisor-connections', JSON.stringify(toSave));
}

function loadLayout() {
    try {
        const saved = localStorage.getItem('supervisor-layout');
        if (saved) return JSON.parse(saved);
    } catch {}
    return null;
}

function saveLayout(items) {
    localStorage.setItem('supervisor-layout', JSON.stringify(items));
}

function persistLayout(grid) {
    const items = grid.save(false);
    const layoutData = items.map(item => {
        const info = activePanels[item.id];
        return {
            x: item.x, y: item.y, w: item.w, h: item.h,
            id: item.id, panelId: info?.panelId, label: info?.label,
        };
    }).filter(item => item.panelId);
    saveLayout(layoutData);
}

// ── Connection Manager ──

class ConnectionManager {
    constructor(onChange) {
        this.onChange = onChange;
        this.sockets = {};       // appId -> WebSocket
        this.manifests = {};     // appId -> manifest
        this.states = {};        // appId -> latest state data
        this.connected = {};     // appId -> boolean
        this.urls = {};          // appId -> WebSocket URL
        this.retryTimers = {};   // appId -> timeout id
        this._staleTimers = {};  // appId -> timeout id
    }

    connect(conns) {
        // Close all existing connections
        for (const appId of Object.keys(this.sockets)) {
            this._close(appId);
        }
        for (const conn of conns) {
            if (conn.enabled) {
                this._open(conn);
            }
        }
    }

    _open(conn) {
        const { app, url } = conn;
        this.urls[app] = url;
        if (this.sockets[app]) this._close(app);

        let ws;
        try {
            ws = new WebSocket(url);
        } catch {
            this.connected[app] = false;
            this._scheduleRetry(conn);
            this.onChange();
            return;
        }

        this.sockets[app] = ws;

        ws.onopen = () => {
            this.connected[app] = true;
            this._resetStaleTimer(app, conn);
            this.onChange();
        };

        ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'manifest') {
                    this.manifests[app] = msg;
                } else if (msg.type === 'state') {
                    this.states[app] = msg.data;
                }
                // Any valid message (including heartbeat) resets the stale timer.
                this._resetStaleTimer(app, conn);
                if (msg.type !== 'heartbeat') this.onChange();
            } catch {}
        };

        ws.onclose = () => {
            this.connected[app] = false;
            this.sockets[app] = null;
            this._clearStaleTimer(app);
            this._scheduleRetry(conn);
            this.onChange();
        };

        ws.onerror = () => {
            // onclose will fire after this
        };
    }

    _resetStaleTimer(appId, conn) {
        this._clearStaleTimer(appId);
        this._staleTimers[appId] = setTimeout(() => {
            // No message received for 10 seconds — force reconnect
            this._close(appId);
            this._scheduleRetry(conn);
            this.onChange();
        }, 10000);
    }

    _clearStaleTimer(appId) {
        if (this._staleTimers[appId]) {
            clearTimeout(this._staleTimers[appId]);
            this._staleTimers[appId] = null;
        }
    }

    _close(appId) {
        this._clearStaleTimer(appId);
        if (this.retryTimers[appId]) {
            clearTimeout(this.retryTimers[appId]);
            this.retryTimers[appId] = null;
        }
        const ws = this.sockets[appId];
        if (ws) {
            ws.onclose = null;
            ws.onerror = null;
            ws.onmessage = null;
            ws.close();
        }
        this.sockets[appId] = null;
        this.connected[appId] = false;
    }

    _scheduleRetry(conn) {
        if (this.retryTimers[conn.app]) return;
        this.retryTimers[conn.app] = setTimeout(() => {
            this.retryTimers[conn.app] = null;
            if (conn.enabled) this._open(conn);
        }, 2000);
    }

    getState(appId) { return this.states[appId] || null; }
    isConnected(appId) { return !!this.connected[appId]; }

    destroy() {
        for (const appId of Object.keys(this.sockets)) {
            this._close(appId);
        }
    }
}

// ── Panel instance tracking ──

let panelCounter = 0;
const activePanels = {};  // instanceId -> { panelId, appId, el }

// ── App Component ──

function App() {
    const [connections, setConnections] = useState(loadConnections);
    const [, setTick] = useState(0);
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [editConns, setEditConns] = useState(null);

    const cmRef = useRef(null);
    const gridRef = useRef(null);

    const forceUpdate = useCallback(() => setTick(t => t + 1), []);

    // Initialize connection manager (once)
    useEffect(() => {
        const cm = new ConnectionManager(forceUpdate);
        cmRef.current = cm;
        return () => cm.destroy();
    }, []);

    // Connect/reconnect when connections change
    useEffect(() => {
        if (cmRef.current) {
            cmRef.current.connect(connections);
        }
    }, [connections]);

    // Initialize Gridstack
    useEffect(() => {
        const grid = window.GridStack.init({
            cellHeight: 60,
            column: 12,
            animate: true,
            float: true,
            handle: '.panel-header',
            removable: false,
        }, '#grid');

        grid.on('change', () => {
            persistLayout(grid);
        });

        gridRef.current = grid;

        // Restore layout
        const saved = loadLayout();
        if (saved && saved.length > 0) {
            for (const item of saved) {
                if (item.panelId) {
                    addPanelToGrid(grid, item.panelId, item);
                }
            }
        }

        return () => grid.destroy(false);
    }, []);

    // Re-render all active panels on state changes
    useEffect(() => {
        const cm = cmRef.current;
        if (!cm) return;
        for (const [instanceId, info] of Object.entries(activePanels)) {
            const renderer = getRenderer(info.panelId);
            if (!renderer) continue;
            const bodyEl = info.bodyEl;
            if (!bodyEl) continue;
            render(html`<${renderer} state=${cm.getState(info.appId)} connected=${cm.isConnected(info.appId)} baseUrl=${wsUrlToHttp(cm.urls[info.appId])} />`, bodyEl);

            // Update header label from manifest if it arrived after the panel was created.
            const manifest = cm.manifests[info.appId];
            const wInfo = manifest?.panels?.find(p => p.id === info.panelId);
            if (wInfo?.name && wInfo.name !== info.label) {
                info.label = wInfo.name;
                const titleEl = info.el?.querySelector('.panel-header-title');
                if (titleEl) titleEl.textContent = wInfo.name;
            }
        }
    });

    function addPanelToGrid(grid, panelId, pos) {
        const renderer = getRenderer(panelId);
        const cm = cmRef.current;
        if (!cm) return;

        // Find manifest info for sizing
        const appId = panelIdToApp(panelId);
        const manifest = cm.manifests[appId];
        const wInfo = manifest?.panels?.find(p => p.id === panelId);

        const instanceId = 'w-' + (++panelCounter);

        const w = pos?.w || wInfo?.default_w || 6;
        const h = pos?.h || wInfo?.default_h || 4;
        const minW = wInfo?.min_w || 2;
        const minH = wInfo?.min_h || 2;
        const x = pos?.x;
        const y = pos?.y;

        const color = APP_COLORS[appId] || 'var(--color-accent)';
        const fallback = panelId.split('.').pop();
        const label = wInfo?.name || pos?.label || fallback.charAt(0).toUpperCase() + fallback.slice(1);

        const opts = { w, h, minW, minH, id: instanceId };
        if (x !== undefined) opts.x = x;
        if (y !== undefined) opts.y = y;

        const el = grid.addWidget(opts);
        el.dataset.panelId = panelId;

        // Build content DOM inside the grid-stack-item-content that Gridstack created
        const contentEl = el.querySelector('.grid-stack-item-content');
        if (contentEl) {
            contentEl.innerHTML = '';

            const header = document.createElement('div');
            header.className = 'panel-header';
            header.innerHTML = `<span class="panel-header-title">${label}</span>`;

            const closeBtn = document.createElement('button');
            closeBtn.className = 'close-btn';
            closeBtn.title = 'Remove panel';
            closeBtn.textContent = '\u00d7';
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                removePanelFromGrid(grid, instanceId);
            });
            header.appendChild(closeBtn);

            const body = document.createElement('div');
            body.className = 'panel-body';

            contentEl.appendChild(header);
            contentEl.appendChild(body);
        }

        const bodyEl = contentEl ? contentEl.querySelector('.panel-body') : null;
        activePanels[instanceId] = { panelId, appId, el, bodyEl, label };

        // Initial render
        if (renderer && bodyEl) {
            render(html`<${renderer} state=${cm.getState(appId)} connected=${cm.isConnected(appId)} baseUrl=${wsUrlToHttp(cm.urls[appId])} />`, bodyEl);
        }

        // Save layout after adding
        persistLayout(grid);
    }

    function removePanelFromGrid(grid, instanceId) {
        const info = activePanels[instanceId];
        if (!info) return;
        if (info.bodyEl) render(null, info.bodyEl);
        grid.removeWidget(info.el);
        delete activePanels[instanceId];
        persistLayout(grid);
    }

    function handleAddPanel(panelId) {
        const grid = gridRef.current;
        if (grid) addPanelToGrid(grid, panelId, undefined);
    }

    function handleResetLayout() {
        const grid = gridRef.current;
        if (!grid) return;
        // Remove all panels
        for (const instanceId of Object.keys(activePanels)) {
            removePanelFromGrid(grid, instanceId);
        }
        localStorage.removeItem('supervisor-layout');
    }

    function handleApplySettings() {
        if (editConns) {
            saveConnections(editConns);
            setConnections(editConns);
            setEditConns(null);
            setSettingsOpen(false);
        }
    }

    const toggleSidebar = useCallback(() => setSidebarOpen(v => !v), []);

    const cm = cmRef.current;

    // Build catalog from manifests
    const catalog = {};
    if (cm) {
        for (const conn of connections) {
            catalog[conn.app] = {
                label: conn.label || conn.app,
                color: APP_COLORS[conn.app],
                connected: cm.isConnected(conn.app),
                panels: cm.manifests[conn.app]?.panels || [],
            };
        }
    }

    return html`
        ${!sidebarOpen ? html`<button id="sidebar-toggle" onClick=${toggleSidebar} title="Show sidebar">\u2630</button>` : null}
        <div id="sidebar" class=${sidebarOpen ? '' : 'collapsed'}>
            <div class="sidebar-header">
                <span>Supervisor</span>
                <button class="sidebar-collapse-btn" onClick=${toggleSidebar} title="Hide sidebar">\u2715</button>
            </div>

            <!-- Panel Catalog -->
            <div class="sidebar-section">
                <div class="sidebar-section-title">Panels</div>
                ${Object.entries(catalog).map(([appId, app]) => html`
                    <div class="sidebar-app-group" key=${appId}>
                        <div class="sidebar-app-label">
                            <span class="app-dot" style="background: ${app.connected ? 'var(--color-active)' : 'var(--color-text-muted)'}; ${app.connected ? 'box-shadow: 0 0 4px var(--color-active)' : 'opacity: 0.4'}"></span>
                            <span>${app.label}</span>
                            <span style="color: var(--color-text-muted); font-weight: 400; font-size: 0.75rem; margin-left: auto">
                                ${app.connected ? 'connected' : 'disconnected'}
                            </span>
                        </div>
                        ${app.panels.length > 0
                            ? app.panels.map(w => html`
                                <div class="sidebar-panel-item" key=${w.id}>
                                    <span class="panel-desc" title=${w.description}>${w.name}</span>
                                    <button onClick=${() => handleAddPanel(w.id)}>+</button>
                                </div>
                            `)
                            : html`<div style="padding-left: 14px; font-size: 0.78rem; color: var(--color-text-muted); font-style: italic">
                                ${app.connected ? 'No panels' : 'Waiting for connection\u2026'}
                            </div>`
                        }
                    </div>
                `)}
            </div>

            <!-- Settings -->
            <div class="sidebar-section">
                <div class="sidebar-section-title" style="cursor: pointer" onClick=${() => { setSettingsOpen(v => !v); if (!settingsOpen) setEditConns(connections.map(c => ({...c}))); }}>
                    Settings ${settingsOpen ? '\u25B4' : '\u25BE'}
                </div>
                ${settingsOpen && editConns ? html`
                    ${editConns.map((conn, i) => html`
                        <div key=${conn.app} style="margin-bottom: 10px">
                            <div style="font-size: 0.82rem; font-weight: 600; margin-bottom: 4px">${conn.label || conn.app}</div>
                            <div class="settings-row">
                                <label>URL</label>
                                <input type="text" value=${conn.url} onInput=${(e) => {
                                    const updated = [...editConns];
                                    updated[i] = { ...updated[i], url: e.target.value };
                                    setEditConns(updated);
                                }} />
                            </div>
                            <div class="settings-row">
                                <label>Enabled</label>
                                <input type="checkbox" checked=${conn.enabled} onChange=${(e) => {
                                    const updated = [...editConns];
                                    updated[i] = { ...updated[i], enabled: e.target.checked };
                                    setEditConns(updated);
                                }} />
                            </div>
                        </div>
                    `)}
                    <div class="settings-buttons">
                        <button class="btn" onClick=${handleApplySettings}>Apply</button>
                        <button class="btn btn--danger" onClick=${handleResetLayout}>Reset Layout</button>
                    </div>
                ` : null}
            </div>
        </div>
        <div id="main">
            <div class="grid-stack" id="grid"></div>
        </div>
    `;
}

// ── Helpers ──

function wsUrlToHttp(wsUrl) {
    if (!wsUrl) return '';
    return wsUrl.replace(/^ws(s?):\/\//, 'http$1://');
}

function panelIdToApp(panelId) {
    const map = {
        'subsequence.': 'subsequence',
        'subsample.': 'subsample',
        'substation.': 'substation',
    };
    for (const [prefix, appId] of Object.entries(map)) {
        if (panelId.startsWith(prefix)) return appId;
    }
    return null;
}

// ── Panel module imports ──
// Each module self-registers via registerPanel()

await Promise.all([
    import('./panels/scanner/channels.js'),
    import('./panels/scanner/recordings.js'),
    import('./panels/sampler/voices.js'),
    import('./panels/sampler/library.js'),
    import('./panels/sampler/recorder.js'),
    import('./panels/sequencer/transport.js'),
    import('./panels/sequencer/patterns.js'),
    import('./panels/sequencer/signals.js'),
]);

// ── Mount ──

render(html`<${App} />`, document.getElementById('app'));
