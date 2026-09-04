# Supervisor

Real-time dashboard for monitoring audio and radio applications via WebSocket.

Supervisor has two parts: a **Python package** that apps import to broadcast their state, and a **browser dashboard** that connects to those apps and displays live panels. The Python package owns the WebSocket server, the state protocol, and the app-specific event bindings. The dashboard owns all panel rendering. This means both sides of the contract live in one repo — they can't drift out of sync.

## Architecture

```
Source app (e.g. Substation scanner)
  │
  │  pip install supervisor
  │
  ├─ imports supervisor.app.substation
  ├─ passes its app instance to SubstationSupervisor(app, port=9004)
  ├─ calls sv.start() / sv.stop()
  │
  └─ app emits events (channel_snr, recording_saved, etc.)
       │
       ▼
  SubstationSupervisor (supervisor/app/substation.py)
  ├─ subscribes to app events
  ├─ accumulates state from events
  ├─ calls mark_dirty() on each change
  │
  └─ BroadcastServer (supervisor/core.py)
     ├─ sends manifest on WebSocket connect
     ├─ broadcasts state at throttled rate (default 2 Hz)
     │
     ▼
  Dashboard (client/)
  ├─ connects via WebSocket
  ├─ receives manifest → populates panel catalog
  ├─ receives state → re-renders panels
  └─ user adds/removes/rearranges panels in a grid
```

## Project layout

```
supervisor/                 Python package (installed by source apps)
  __init__.py
  core.py                   BroadcastServer base class
  app/
    __init__.py
    substation.py            Scanner integration
client/                     Dashboard frontend (static files, no build step)
  index.html
  app.js                    Connection manager, Gridstack, sidebar
  style.css                 Theme, colour palette, panel CSS
  lib/                      Vendored Gridstack.js
  components/               Reusable UI components (used by panels)
    led-meter.js             LedMeter segmented indicator
    utils.js                 valueToOpacity and other helpers
  panels/                   App-specific panel renderers (self-registering)
    registry.js
    scanner/
    sampler/
    sequencer/
tests/                      pytest tests
mocks/                      Mock WebSocket servers for development
serve.py                    Dev server (serves client/ on port 8000)
pyproject.toml
```

## Running the dashboard

```bash
python serve.py
```

Opens http://localhost:8000. The dashboard connects to configured WebSocket URLs (editable in the Settings panel) and auto-reconnects if an app isn't running yet.

## WebSocket protocol

All messages are JSON with a `type` field. The server sends two message types to the dashboard.

### Manifest (sent once on connect)

Describes the app and its available panels.

```json
{
  "type": "manifest",
  "app": "substation",
  "label": "Scanner",
  "color": "#d2a8ff",
  "panels": [
    {
      "id": "scanner.channels",
      "name": "Channels",
      "description": "Channel states, frequencies, SNR levels",
      "default_w": 6, "default_h": 6,
      "min_w": 4, "min_h": 3
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `app` | string | Machine-readable app identifier (e.g. `"substation"`, `"subsequence"`) |
| `label` | string | Human-readable name shown in the sidebar |
| `color` | string | CSS colour for panel accent borders |
| `panels` | array | Available panel types (see below) |

Each panel entry:

| Field | Type | Description |
|---|---|---|
| `id` | string | Globally unique, prefixed with a short app name (e.g. `"scanner.channels"`) |
| `name` | string | Short display name |
| `description` | string | One-line description for the catalog |
| `default_w`, `default_h` | int | Default grid size (12-column grid) |
| `min_w`, `min_h` | int | Minimum grid size |

### State (broadcast periodically)

The app's current state. Sent whenever state changes, throttled to avoid flooding.

```json
{
  "type": "state",
  "data": { ... }
}
```

The `data` object is app-specific. Each panel knows which fields to read from it. The dashboard stores the latest state per app and passes it to that app's panels on every update.

## Integrating a new app

Adding a new source app requires changes in two places: a Python module in `supervisor/app/` (server side) and panel JS files in `client/panels/` (dashboard side).

### Step 1: Define the app module

Create `supervisor/app/yourapp.py`. This module defines the manifest and translates your app's events into dashboard state.

```python
import supervisor.core

MANIFEST = {
    "type": "manifest",
    "app": "yourapp",              # machine-readable, matches project name
    "label": "yourapp",           # shown in sidebar, lowercase
    "color": "#ff9800",           # accent colour
    "panels": [
        {
            "id": "yourapp.status",
            "name": "Status",
            "description": "Current app status",
            "default_w": 6, "default_h": 3,
            "min_w": 3, "min_h": 2,
        },
    ],
}


class YourAppSupervisor(supervisor.core.BroadcastServer):

    def __init__(self, app, port=9005):
        super().__init__(manifest=MANIFEST, port=port)

        # Read any static config from the app instance.
        self._name = app.name

        # Subscribe to app events.
        app.on('status_changed', self._on_status_changed)

    def _on_status_changed(self, **kwargs):
        self._status = kwargs.get('status', 'unknown')
        self.mark_dirty()     # triggers broadcast on next tick

    def get_state(self):
        """Return the full state dict. Called by BroadcastServer."""
        return {
            "name": self._name,
            "status": self._status,
        }
```

Key points:
- Subclass `BroadcastServer` and pass your manifest to `super().__init__()`.
- Subscribe to your app's events in `__init__`. Each handler should update internal state and call `self.mark_dirty()`.
- Override `get_state()` to return a JSON-serializable dict. This is what the dashboard receives as `data` in state messages.
- The base class handles WebSocket lifecycle, client management, and throttled broadcasting. You never touch sockets directly.
- **Broadcast rate**: `BroadcastServer` accepts a `max_hz` parameter (default `2.0`) that throttles how often state is sent. The broadcast loop only sends when state is dirty AND the minimum interval has elapsed. Override in your subclass: `super().__init__(manifest=MANIFEST, port=port, max_hz=5.0)`.
- **`after_broadcast()`**: Override this hook to reset accumulated state after each broadcast. Called after state is sent to all clients. Use it to clear peak values or mark data for replacement, so the next broadcast cycle accumulates fresh readings.
- **File serving**: `BroadcastServer` accepts a `serve_dirs` parameter — a list of absolute directory paths that the server is allowed to serve over HTTP. Files are accessible at `http://host:port/audio/<relative-path>`. This allows dashboard panels to play audio files or download artifacts from the app's machine. Path traversal is blocked via `os.path.realpath` validation. No `serve_dirs` = no file serving (opt-in only). Example: `super().__init__(manifest=MANIFEST, port=port, serve_dirs=["/path/to/audio"])`.

#### File paths in state data

When your app produces files (recordings, samples, etc.), send a **relative path** and **filename** rather than the full absolute path:

```python
abs_path = kwargs.get('file_path', '')
rel_path = os.path.relpath(abs_path, self._audio_dir) if abs_path else ''
filename = os.path.basename(abs_path) if abs_path else ''
# Store: {"path": rel_path, "filename": filename}
```

The dashboard displays `filename` and constructs the audio URL from `http://host:port/audio/{path}`. This avoids exposing absolute server paths to the browser.

#### Threading considerations

Source apps often emit events from background threads (e.g. an executor running signal processing). The broadcast loop and `get_state()` run on the asyncio event loop thread. If your event handlers are called from a different thread:

- **Prefer atomic reference swaps over locks.** Build a new list/dict in the handler and assign it to `self._field` in one statement. Under CPython's GIL, reference assignment is atomic. `get_state()` reads the reference — it always gets a consistent snapshot. Never mutate a shared list/dict in place from a background thread.
- **Do not use `threading.Lock`** on the event loop thread — a blocking lock stalls the entire event loop, killing all WebSocket I/O.
- **Check how events are delivered**: if the source app uses `call_soon_threadsafe` (or equivalent), the handler runs on the event loop thread and no synchronisation is needed. If it calls handlers directly from a worker thread, use atomic swaps as above. Different events in the same app may use different delivery mechanisms.
- **Sanitise numpy types**: if the source app uses numpy, values like `numpy.bool_` or `numpy.float64` are not JSON-serializable on Python 3.13+. Convert to native Python types (`bool()`, `float()`, `int()`) before storing.

The substation integration is a working example of this pattern — see `supervisor/app/substation.py`.

#### State accumulation between broadcasts

Since the broadcast rate is throttled (default 2 Hz) but events may arrive much faster (5–50 Hz), your app module should accumulate state intelligently between broadcasts:

- **Don't just store the latest snapshot** — you'll miss brief peaks. Merge incoming data, keeping the most interesting values (e.g. highest SNR, any `is_active=True`).
- **Use `after_broadcast()` to start a fresh accumulation cycle** — but don't clear data to empty, or the dashboard will briefly show "no data" if the next event is delayed. Instead, flag data for replacement on the next event arrival.
- **Use authoritative events for state transitions** — if your app emits both continuous snapshots (like SNR readings) and discrete transition events (like channel ON/OFF), track the transitions separately and merge them in `get_state()`. The transitions are authoritative; the snapshots may be stale due to threading.

### Step 2: Wire it into your app

In your app's startup code, conditionally import and start the supervisor:

```python
# In your app's main/CLI code:
async def run():
    app = YourApp(config)

    sv = None
    if config.supervisor_enabled:
        try:
            from supervisor.app.yourapp import YourAppSupervisor
            sv = YourAppSupervisor(app, port=config.supervisor_port)
            await sv.start()
        except ImportError:
            logger.warning("Supervisor not installed")

    try:
        await app.run()
    finally:
        if sv:
            await sv.stop()
```

Add Supervisor as an optional dependency in your app's `pyproject.toml`:

```toml
[project.optional-dependencies]
supervisor = [
    "supervisor @ git+https://github.com/OWNER/Supervisor.git",
]
```

Install with `pip install -e ".[supervisor]"`.

### Step 3: Create the dashboard panel

Create `client/panels/yourapp/status.js`:

```javascript
import { h } from 'https://esm.sh/preact@10.19.6';
import htm from 'https://esm.sh/htm@3.1.1';
import { registerPanel } from '../registry.js';

const html = htm.bind(h);

function StatusPanel({ state, connected }) {
    if (!connected) {
        return html`<div class="panel-disconnected">Your App not connected</div>`;
    }
    if (!state) {
        return html`<div class="panel-disconnected">Waiting for data...</div>`;
    }

    return html`
        <div>
            <div class="panel-kv">
                <span class="panel-kv-label">Name</span>
                <span class="panel-kv-value">${state.name}</span>
            </div>
            <div class="panel-kv">
                <span class="panel-kv-label">Status</span>
                <span class="panel-kv-value">${state.status}</span>
            </div>
        </div>
    `;
}

registerPanel('yourapp.status', StatusPanel);
```

Every panel receives two props:
- `connected` (boolean) — whether the WebSocket is open
- `state` (object or null) — the latest `data` from a state message

Build panels from the shared CSS classes in `style.css`: `.panel-kv`, `.panel-gauge`, `.panel-table`, `.panel-status`, `.panel-log`, `.panel-empty`, `.panel-section`.

### Step 4: Register the panel and connection

In `client/app.js`, add the import and connection config:

```javascript
// Add to the DEFAULT_CONNECTIONS array:
{ app: 'yourapp', label: 'yourapp', url: 'ws://localhost:9005', enabled: true },

// Add to APP_COLORS:
yourapp: 'var(--yourapp-color)',

// Add to panelIdToApp():
'yourapp.': 'yourapp',

// Add to the panel import list:
import('./panels/yourapp/status.js'),
```

Add your colour variable to `client/style.css`:

```css
--yourapp-color: #ff9800;
```

### Step 5: Write tests

Add tests in `tests/` following the existing pattern. Test the manifest structure and the `get_state()` output from event sequences. Use a lightweight stub for your app instance (see `tests/conftest.py` for an example).

## Existing app integrations

### substation (SDR scanner)

- **Module**: `supervisor/app/substation.py`
- **Port**: 9004
- **Events consumed**: `channel_snr`, `channel_state`, `noise_floor`, `recording_started`, `recording_saved`, `recording_discarded`
- **Panels**: `substation.channels` (channel state table), `substation.recordings` (active/recent recordings)

### subsequence (MIDI sequencer)

- **Module**: not yet created (mock only)
- **Port**: 8765
- **Panels**: `subsequence.transport`, `subsequence.patterns`, `subsequence.signals`

### subsample (sampler)

- **Module**: not yet created (mock only)
- **Port**: 9003
- **Panels**: `subsample.voices`, `subsample.library`, `subsample.recorder`

## UI components

Reusable elements for building panels. Preact components live in `client/components/`. CSS classes are defined in `client/style.css`.

### Colour palette

All colours are defined as CSS custom properties in `:root` in `client/style.css`. Use these — never hardcode hex values.

| Variable | Value | Usage |
|---|---|---|
| `--color-bg` | `#0d1117` | Page background |
| `--color-bg-raised` | `#161b22` | Panel backgrounds, sidebar |
| `--color-border` | `#30363d` | Borders, dividers, scrollbar |
| `--color-text` | `#c9d1d9` | Primary text |
| `--color-text-muted` | `#8b949e` | Secondary text, labels |
| `--color-active` | `#3fb950` | Green — connected, active, success |
| `--color-warning` | `#d29922` | Amber — backlog, threshold |
| `--color-error` | `#ff7b72` | Red — error, danger |
| `--color-accent` | `#58a6ff` | Blue — default accent |
| `--color-app-subsequence` | `#58a6ff` | App identity: subsequence |
| `--color-app-subsample` | `#3fb950` | App identity: subsample |
| `--color-app-substation` | `#d2a8ff` | App identity: substation |

### LED Meter (`LedMeter`)

**File**: `client/components/led-meter.js`

Segmented level indicator — like a classic VU meter. Import and use in any panel:

```javascript
import { LedMeter } from '../../components/led-meter.js';

html`<${LedMeter} value=${12.5} min=${-10} max=${30} segments=${8} />`
```

| Prop | Type | Default | Description |
|---|---|---|---|
| `value` | number | required | Current value to display |
| `min` | number | `0` | Value where all segments are off |
| `max` | number | `100` | Value where all segments are fully on |
| `segments` | number | `8` | Number of LED blocks |
| `scale` | `'linear'` \| `'log'` | `'linear'` | Value-to-position mapping |
| `direction` | `'horizontal'` \| `'vertical'` | `'horizontal'` | Layout direction (vertical fills bottom to top) |

Segments fill proportionally: fully on, partially on (reduced opacity), or off. A white glow is applied in proportion to each segment's fill level.

### Audio Player (`AudioPlayer`)

**File**: `client/components/audio-player.js`

Inline play/stop button that streams audio from the app's server. Requires `serve_dirs` to be configured on the `BroadcastServer`.

```javascript
import { AudioPlayer } from '../../components/audio-player.js';

// src is the full HTTP URL to the audio file
html`<${AudioPlayer} src=${'http://host:9004/audio/2026-04-14/recording.wav'} />`
```

| Prop | Type | Default | Description |
|---|---|---|---|
| `src` | string | required | Full HTTP URL of the audio file |

Displays ▶ when stopped, ■ when playing. Green while playing. The browser's native `<audio>` element handles decoding — supports WAV, FLAC, MP3, OGG.

Every panel receives a `baseUrl` prop (the HTTP equivalent of the app's WebSocket URL). Construct audio URLs with: `` `${baseUrl}/audio/${recording.path}` ``

**Future**: transcoding support for formats the browser can't play, or for compressing large files over slow networks. Not yet implemented.

### Value-to-Opacity (`valueToOpacity`)

**File**: `client/components/utils.js`

Maps a value to an opacity for visual emphasis on rows or elements. Uses a square root curve so low values rise quickly while high values compress. Useful for making table rows or list items brighter when their value is higher (e.g. SNR, MIDI velocity, confidence scores).

```javascript
import { valueToOpacity } from '../../components/utils.js';

// In a table row:
html`<tr style="opacity: ${valueToOpacity(snr_db, 0, 20)}">...</tr>`

// MIDI velocity example:
html`<tr style="opacity: ${valueToOpacity(velocity, 0, 127)}">...</tr>`
```

| Param | Type | Default | Description |
|---|---|---|---|
| `value` | number | required | Input value |
| `min` | number | required | Value at or below which opacity = floor |
| `max` | number | required | Value at or above which opacity = 1.0 |
| `floor` | number | `0.2` | Minimum opacity (returned when value <= min) |

### Key-Value Row (`.panel-kv`)

Horizontal label + value pair.

```html
<div class="panel-kv">
    <span class="panel-kv-label">BPM</span>
    <span class="panel-kv-value">120.0</span>
</div>
```

### Gauge Bar (`.panel-gauge`)

Horizontal fill bar with label and value.

```html
<div class="panel-gauge">
    <div class="panel-gauge-header">
        <span class="panel-gauge-label">Memory</span>
        <span class="panel-gauge-value">45 / 100 MB</span>
    </div>
    <div class="panel-gauge-track">
        <div class="panel-gauge-fill" style="width: 45%"></div>
    </div>
</div>
```

### Status Dot (`.panel-status`)

Active/inactive indicator with label.

```html
<span class="panel-status">
    <span class="panel-status-dot panel-status-dot--active"></span>
    Active
</span>
```

Modifiers: `--active` (bright), `--inactive` (dim), `--warning`.

### Data Table (`.panel-table`)

Compact table with sticky headers. Row modifiers: `.panel-table-row--active` (subtle highlight), `.panel-table-row--dimmed` (reduced opacity).

### Event Log (`.panel-log`)

Reverse-chronological list of timestamped items.

```html
<ul class="panel-log">
    <li class="panel-log-item">
        <span class="panel-log-time">12:30</span>
        <span class="panel-log-message">Recording saved</span>
    </li>
</ul>
```

### Section Header (`.panel-section`)

Subtle sub-heading to separate groups within a panel body.

### Empty State (`.panel-empty`)

Centred italic message for when a panel has no data.

### Disconnected State (`.panel-disconnected`)

Centred italic message for when the app is not connected or has no state yet.

## Development

```bash
# Create a venv and install with dev dependencies
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run the dashboard dev server
python serve.py

# Run mock servers for testing (requires websockets)
python mocks/mock_scanner.py
python mocks/mock_sampler.py
python mocks/mock_sequencer.py
```

### Installing in a source app's venv

During development, install as an **editable local path** so changes take effect immediately:

```bash
pip install -e /path/to/Supervisor
```

Do **not** install from the Git URL during active development — pip caches the version number and won't re-fetch unless you bump it or use `--force-reinstall`.

### Avoiding stale bytecode

Python's `.pyc` cache can serve old code on network/mounted filesystems even after the source changes. To prevent this, set the environment variable before running the source app:

```bash
export PYTHONDONTWRITEBYTECODE=1
```

Or use `python -B` when launching directly. This disables `.pyc` generation entirely — negligible performance cost for long-running apps.

## Technology

- **Server**: Python 3.11+, websockets
- **Dashboard**: Preact 10 + htm (CDN, no build step), Gridstack.js 12 (vendored), JetBrains Mono (data font)
- **License**: AGPL-3.0
