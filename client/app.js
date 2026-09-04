/* The panel.
 *
 * One socket to the service, one grid on the glass. Three rules shape all of
 * it, and they come from Subroutine #2046:
 *
 *   1. A cell's face is always the sequencer's value. Nothing drawn on a face
 *      is a guess, so two panels can never disagree about what will sound.
 *   2. An unconfirmed tap draws a ring. The ring is the request; it clears
 *      when the sequencer says the change landed, a few milliseconds later.
 *   3. A tap acts on the finger landing, not on it lifting.
 */

import { html, render, useState, useEffect, useRef, useCallback }
	from "./vendor/htm-preact-standalone.module.js";

const PING_EVERY = 2000;
const STALE_AFTER = 6000;
const RECONNECT_FLOOR = 250;
const RECONNECT_CEILING = 5000;
const PENDING_EXPIRES = 5000;

const clientId = `panel-${Math.random().toString(36).slice(2, 10)}`;

/* ------------------------------------------------------------------ */
/* The link                                                            */
/* ------------------------------------------------------------------ */

/* Holds the socket, keeps it up, and hands whole frames to the page.
 *
 * Liveness has to be our own: a server that has stopped answering but not
 * closed its socket is invisible to the browser for half a minute, so we ping
 * and we time out rather than trusting the connection to fail loudly. */
class Link {
	constructor (onFrame, onStatus) {
		this.onFrame = onFrame;
		this.onStatus = onStatus;
		this.socket = null;
		this.delay = RECONNECT_FLOOR;
		this.seq = 0;
		this.lastInbound = 0;
		this.timers = [];
		this.dial();
	}

	dial () {
		const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/panel`;
		this.socket = new WebSocket(url);

		this.socket.onopen = () => {
			this.delay = RECONNECT_FLOOR;
			this.lastInbound = performance.now();
			this.onStatus("up");
			this.send({ t: "hello", contract: "1.0.0", client: clientId, page: "grid", ver: {}, token: null });
		};

		this.socket.onmessage = (message) => {
			this.lastInbound = performance.now();

			try {
				this.onFrame(JSON.parse(message.data));
			} catch (error) {
				console.warn("unreadable frame", error);
			}
		};

		this.socket.onclose = () => this.fell();
		this.socket.onerror = () => this.socket && this.socket.close();

		this.timers.forEach(clearInterval);
		this.timers = [
			setInterval(() => this.send({ t: "ping", ts: performance.now() }), PING_EVERY),
			setInterval(() => {
				if (performance.now() - this.lastInbound > STALE_AFTER && this.socket) this.socket.close();
			}, 1000),
		];
	}

	fell () {
		this.timers.forEach(clearInterval);
		this.timers = [];
		this.socket = null;
		this.onStatus("down");

		/* Jittered, so a room full of panels does not return in step. */
		const wait = this.delay * (0.7 + Math.random() * 0.6);
		this.delay = Math.min(this.delay * 2, RECONNECT_CEILING);
		setTimeout(() => this.dial(), wait);
	}

	send (frame) {
		if (this.socket && this.socket.readyState === WebSocket.OPEN) {
			this.socket.send(JSON.stringify(frame));
			return true;
		}
		return false;
	}

	/* Absolute, never a toggle: sending it twice reaches the same grid as
	 * sending it once, which is what makes a reconnect re-send safe. */
	set (app, path, value) {
		const seq = ++this.seq;
		return this.send({ t: "set", app, path, v: value, seq }) ? seq : null;
	}
}

/* ------------------------------------------------------------------ */
/* The grid                                                            */
/* ------------------------------------------------------------------ */

function Grid ({ control, rows, steps, cells, pending, failed, onTap }) {
	/* A fixed label column, then one equal column per step. */
	const style = {
		gridTemplateColumns: `minmax(6.5rem, max-content) repeat(${steps}, minmax(44px, 1fr))`,
	};

	return html`
		<div class="grid" style=${style}>
			${rows.map((row) => html`
				<div class="row-label" key=${`label-${row}`}>${row.replace(/_/g, " ")}</div>
				${Array.from({ length: steps }, (_, step) => {
					const path = `${control}/${row}/${step}`;
					const on = (cells[row] || []).includes(step);

					return html`
						<div
							key=${path}
							class=${["cell", on ? "on" : "", pending.has(path) ? "pending" : "",
								failed.has(path) ? "failed" : "",
								step % 4 === 0 ? "downbeat" : ""].filter(Boolean).join(" ")}
							onPointerDown=${(event) => { event.preventDefault(); onTap(path, !on); }}
						></div>`;
				})}
			`)}
		</div>`;
}

/* The highlight tracking what is sounding.
 *
 * The sequencer reports beats, not steps: between two of them the position is
 * worked out here, so the highlight moves smoothly instead of hopping four
 * times a bar. It is moved by transform alone, which keeps it off the layout
 * path — the grid itself is never re-laid-out to animate it. */
function Playhead ({ anchor, steps, beats }) {
	const bar = useRef(null);

	useEffect(() => {
		if (!anchor || !bar.current) return;

		let frame;
		const grid = bar.current.parentElement.querySelector(".grid");

		const move = () => {
			const cells = grid && grid.children[1];

			if (cells && anchor.interval) {
				const elapsed = (performance.now() - anchor.at) / 1000;
				const beatNow = anchor.beat + Math.min(elapsed / anchor.interval, 1);
				const step = (beatNow * (steps / beats)) % steps;

				const width = cells.getBoundingClientRect().width + 4;
				const left = cells.offsetLeft;

				bar.current.style.width = `${width}px`;
				bar.current.style.transform = `translateX(${left + step * width}px)`;
			}

			frame = requestAnimationFrame(move);
		};

		move();
		return () => cancelAnimationFrame(frame);
	}, [anchor, steps, beats]);

	return html`<div class="playhead" ref=${bar}></div>`;
}

/* Silence and tempo.
 *
 * Both faces show what the sequencer holds, never what was last tapped — the
 * same rule the cells follow. Silence is not a pause: the clock runs on
 * underneath it, so lifting it drops you where the music has got to. */
function Transport ({ control, name, fields, up, onSet }) {
	const silenced = fields.silenced === true;
	const bpm = fields.bpm;
	const [low, high] = control.tempo_range || [40, 240];

	const nudge = (by) => {
		if (typeof bpm !== "number") return;
		onSet(`${name}/bpm`, Math.min(high, Math.max(low, Math.round((bpm + by) * 10) / 10)));
	};

	return html`
		<div class="transport">
			<button
				class=${`silence ${silenced ? "engaged" : ""}`}
				disabled=${!up}
				onPointerDown=${(event) => { event.preventDefault(); onSet(`${name}/silenced`, !silenced); }}
			>${silenced ? "SILENCED" : "SILENCE"}</button>

			<div class="tempo">
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(-5); }}>−5</button>
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(-1); }}>−1</button>
				<span class="reading">${typeof bpm === "number" ? bpm.toFixed(bpm % 1 ? 1 : 0) : "—"}<i>BPM</i></span>
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(1); }}>+1</button>
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(5); }}>+5</button>
			</div>
		</div>`;
}

/* ------------------------------------------------------------------ */
/* The page                                                            */
/* ------------------------------------------------------------------ */

function Panel () {
	const [status, setStatus] = useState("down");
	const [apps, setApps] = useState({});
	const [present, setPresent] = useState({});
	const [state, setState] = useState({});
	const [anchor, setAnchor] = useState(null);
	const [pending, setPending] = useState(new Map());
	const [failed, setFailed] = useState(new Set());

	const link = useRef(null);
	const expiries = useRef(new Map());

	const drop = useCallback((path) => {
		setPending((was) => {
			if (!was.has(path)) return was;
			const now = new Map(was);
			now.delete(path);
			return now;
		});

		const timer = expiries.current.get(path);
		if (timer) { clearTimeout(timer); expiries.current.delete(path); }
	}, []);

	/* A brief mark on a cell whose request did not land. It is not a state the
	 * cell is in — the face never moved — so it fades by itself. */
	const flashFailure = useCallback((path) => {
		if (!path) return;

		setFailed((was) => new Set(was).add(path));
		setTimeout(() => setFailed((was) => {
			const now = new Set(was);
			now.delete(path);
			return now;
		}), 900);
	}, []);

	useEffect(() => {
		const onFrame = (frame) => {
			switch (frame.t) {
				case "manifest": {
					/* Declarations are remembered rather than replaced: an app that
					 * has gone should leave its grid on the glass, greyed, rather
					 * than take the page down with it. */
					const listed = frame.apps || {};
					setApps((was) => ({ ...was, ...listed }));
					setPresent((was) => {
						const now = {};
						for (const name of new Set([...Object.keys(was), ...Object.keys(listed)])) {
							now[name] = name in listed;
						}
						return now;
					});
					break;
				}

				case "app":
					setPresent((was) => ({ ...was, [frame.app]: frame.up }));
					break;

				case "snapshot":
					setState((was) => ({ ...was, [frame.app]: frame.state || {} }));
					break;

				case "changed": {
					/* The face follows the sequencer, whoever moved it. */
					const [control, row, step] = frame.path.split("/");
					setState((was) => {
						const app = { ...(was[frame.app] || {}) };
						const grid = { ...(app[control] || {}) };
						const list = new Set(grid[row] || []);
						frame.v ? list.add(Number(step)) : list.delete(Number(step));
						grid[row] = [...list].sort((a, b) => a - b);
						app[control] = grid;
						return { ...was, [frame.app]: app };
					});

					if (frame.client === clientId) drop(frame.path);
					break;
				}

				case "ack":
					break;

				case "nack":
					/* The request was refused: the ring goes and the cell says so
					 * briefly. The face never moved, so there is nothing to undo. */
					drop(frame.path);
					flashFailure(frame.path);
					console.warn("refused", frame.path, frame.reason);
					break;

				case "event":
					if (frame.name === "beat") {
						setAnchor({ beat: frame.beat, at: performance.now(), interval: frame.interval });
					}
					break;
			}
		};

		link.current = new Link(onFrame, setStatus);
	}, [drop, flashFailure]);

	const request = useCallback((path, value) => {
		const app = Object.keys(apps)[0];
		if (!app || !link.current) return;

		const seq = link.current.set(app, path, value);
		if (seq === null) return;

		setPending((was) => new Map(was).set(path, seq));

		/* A ring that is never confirmed must not sit there for ever: after
		 * five seconds the request is abandoned and the face — which was
		 * always the truth — is all that is left. */
		expiries.current.set(path, setTimeout(() => { drop(path); flashFailure(path); }, PENDING_EXPIRES));
	}, [apps, drop, flashFailure]);

	const appName = Object.keys(apps)[0];
	const controls = appName ? apps[appName] : {};
	const controlName = Object.keys(controls).find((name) => controls[name].type === "step_grid");
	const up = appName ? present[appName] !== false : false;

	if (!controlName) {
		return html`
			<div class="bar"><span class="title">Superintendent</span><span class="spacer"></span>
				<span class=${`lamp ${status === "up" ? "up" : ""}`}>${status === "up" ? "connected" : "offline"}</span>
			</div>
			<div class="notice">
				${status === "up"
					? "Waiting for a music app to dial in and say what it offers."
					: "Waiting for the Superintendent service."}
			</div>`;
	}

	const control = controls[controlName];
	const cells = (state[appName] || {})[controlName] || {};

	const transportName = Object.keys(controls).find((name) => controls[name].type === "transport");
	const transportFields = transportName ? (state[appName] || {})[transportName] || {} : {};

	return html`
		<div class="bar">
			${transportName && html`
				<${Transport} control=${controls[transportName]} name=${transportName}
					fields=${transportFields} up=${up} onSet=${request} />`}
			<span class="spacer"></span>
			${!up && html`<span class="warn">not running — taps will be refused</span>`}
			<span class=${`lamp ${status === "up" && up ? "up" : ""}`}>
				${status !== "up" ? "no service" : up ? "connected" : "app gone"}
			</span>
		</div>
		<div class=${`grid-wrap ${up ? "" : "absent"}`}>
			<${Grid} control=${controlName} rows=${control.rows} steps=${control.steps}
				cells=${cells} pending=${pending} failed=${failed} onTap=${request} />
			${up && html`<${Playhead} anchor=${anchor} steps=${control.steps} beats=${control.beats || 4} />`}
		</div>`;
}

render(html`<${Panel} />`, document.getElementById("panel"));

/* A long press must not offer a context menu, and a double tap must not zoom:
 * both are the browser deciding a musician's gesture means something else. */
document.addEventListener("contextmenu", (event) => event.preventDefault());
document.addEventListener("gesturestart", (event) => event.preventDefault());
