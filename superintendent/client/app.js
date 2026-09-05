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

import { html, render, useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo }
	from "./vendor/htm-preact-standalone.module.js";

const PING_EVERY = 2000;
const STALE_AFTER = 6000;
const RECONNECT_FLOOR = 250;
const RECONNECT_CEILING = 5000;
const PENDING_EXPIRES = 5000;

const clientId = `panel-${Math.random().toString(36).slice(2, 10)}`;

/* Which page this browser is actually running.
 *
 * The service stamps the build into the script's own URL, which is the only
 * place a module can read its own identity from without being told it. A page
 * served by something that does not stamp it has none, and then says nothing
 * rather than claiming to match (#2056). */
const pageBuild = new URL(import.meta.url).searchParams.get("v");

/* Which page this panel is showing, and where that choice is kept.
 *
 * A composition offers several views over its own controls and every panel
 * loads the same URL, so the choice belongs to the panel rather than to the
 * service (#2075). Kept in this browser's storage, which is what lets each
 * performer pick their own without accounts, a login or a user model — and
 * what returns a player to their own page after a reload rather than to
 * somebody else's default, which matters most in the middle of a set.
 *
 * A `?page=` in the address wins, so a performer's tablet can be pointed once
 * and left alone. */
const PAGE_KEY = "superintendent.page";
const PAGE_BUTTONS = 6;

const SEPARATION = 1;
/* Cells of air left between blocks that nobody has placed. */

const ARROW = 9;
/* How long the head of a connecting line is, in pixels.
 *
 * Not scaled by the cell. It is a mark rather than a control: nobody touches it,
 * and at the smallest size a proportional arrowhead would be three pixels of
 * nothing. */

const PINCH_THRESHOLD = 0.12;
/* How far two fingers must move apart or together before it is a pinch.
 *
 * There has to be a threshold, and this is what it protects: two fingers on a
 * grid are two taps. Playing several cells at once is the reason multi-touch
 * was measured at all (#1997), and a gesture that claimed the second finger
 * would take that away. Two fingers that land and stay put switch two steps; it
 * is only when the distance between them changes by an eighth that this becomes
 * a size. A cell is switched on press (#2046), so those two taps have already
 * happened by then and are not taken back — which is right: the person did tap
 * two cells, and then went on to do something else. */
const CHOICE_BUTTONS = 4;


function askedForPage () {
	return new URL(location.href).searchParams.get("page");
}

function rememberedPage () {
	try {
		return askedForPage() || localStorage.getItem(PAGE_KEY);
	} catch (error) {
		return askedForPage();
	}
}

/* The sizes a cell can be, and where the choice is kept.
 *
 * None of these is the right one. A target that suits one pair of hands is
 * wrong for another, and a step grid at half the width fits twice the music on
 * the same glass — which is what Simon asked for after using the panel. So the
 * size is a setting with a recommended default, not a number chosen here
 * (#2055). "Fit" is not a size but a rule: measure the glass in front of you,
 * rather than the 1920-by-1080 one this was developed on (#2050).
 *
 * 44 px is the size the proof-of-concept was tested at, with taps landing where
 * intended and palm rejection working (#1998), so it is the one named "tested".
 * The others are offered without evidence and the label says so. */
const LOCK_KEY = "superintendent.layout-locked";

/* Whether the layout is held still. Remembered, because a person who works
   with it unlocked should not have to say so again every time they reload —
   Simon's own words were that they may choose to leave it unlocked all the
   time. Locked is the default: an unintended drag costs a layout, and a
   deliberate one costs a tap. */
function rememberedLock () {
	try {
		return localStorage.getItem(LOCK_KEY) !== "no";
	} catch (error) {
		return true;
	}
}

function rememberLock (locked) {
	try {
		localStorage.setItem(LOCK_KEY, locked ? "yes" : "no");
	} catch (error) {
		/* A browser that will not remember is not a browser that cannot work. */
	}
}

const SIZE_KEY = "superintendent.cell-size";

const SIZES = [
	{ key: "fit", label: "Fit the glass", px: null },
	{ key: "compact", label: "Compact", px: 22 },
	{ key: "snug", label: "Snug", px: 32 },
	{ key: "tested", label: "Tested", px: 44 },
	{ key: "large", label: "Large", px: 60 },
	{ key: "huge", label: "Huge", px: 96 },
];

const FIT_FLOOR = 22;
const FIT_CEILING = 96;
const FIT_SLACK = 2;

const GAP = 4;
const LABEL_CELLS = 3;
const TITLE_FLOOR = 24;
const LANE_CELLS = 3;
const PARAM_CELLS = 6;
/* A control's row is one cell. The same cell as everything else.
 *
 * This had a 44px floor under it, on the grounds that a control must stay
 * pressable however small the grid beside it is set (#2055). The floor is
 * gone, and the argument that removed it is that a *step cell* is the most
 * tapped thing on this whole surface and shrinks to 22px without complaint.
 * Protecting a switch from a size a person is happily playing at was not a
 * trade-off, it was an inconsistency — and it was visible: at the compact size
 * the pattern shrank and the settings beside it stayed put.
 *
 * The size is the person's choice (#2055) and it now governs everything they
 * chose it for. If 22px turns out to be too small to work with, that is an
 * argument against 22px rather than for a control that ignores it. */
function controlRow (cell) {
	return cell;
}

const DRAWN = ["step_grid", "note_grid", "params", "recipe"];
/* The kinds a page draws as blocks of their own. A transport is not among them:
   it belongs in the header, with what is constant across pages (#2075). */
/* The gap between cells, how many of them the row labels span, and the height
   a title bar will not go below. GAP is written in the stylesheet too and the
   two must agree; there is a test that says so. */
const DEFAULT_SIZE = "fit";

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
			this.send({ t: "hello", contract: "1.6.0", client: clientId, page: rememberedPage(), ver: {}, token: null });
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
			setInterval(() => {
				if (!document.hidden) this.send({ t: "ping", ts: performance.now() });
			}, PING_EVERY),
			setInterval(() => {
				if (document.hidden) return;
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

	/* Say hello again on a socket that is already open, or dial at once if it
	 * is not. A hidden tab's timers are throttled to once a minute, so a panel
	 * waking up cannot be left to its own stale timer to notice. */
	resync () {
		if (this.socket && this.socket.readyState === WebSocket.OPEN) {
			this.send({ t: "hello", contract: "1.6.0", client: clientId, page: rememberedPage(), ver: {}, token: null });
			return;
		}

		this.delay = RECONNECT_FLOOR;
		if (!this.socket) this.dial();
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

	/* Where a page's parts sit, handed back to the app that owns the page.
	 * Positions in lattice cells and no sizes, in the order the parts are
	 * stacked — so the last entry is the one on top (#2078). */
	layout (app, page, parts) {
		const seq = ++this.seq;
		return this.send({ t: "layout", app, page, parts, client: clientId, seq }) ? seq : null;
	}
}

/* ------------------------------------------------------------------ */
/* The grid                                                            */
/* ------------------------------------------------------------------ */

/* A window onto a control taller than the block showing it.
 *
 * Shared by every kind of grid on purpose. Two octaves is twenty-five rows
 * against a drum machine's ten, so pitched patterns need it first — but a drum
 * machine with forty voices needs exactly the same thing, and two
 * implementations of it would be two chances to behave differently.
 *
 * Only what is inside scrolls. A velocity lane and a playhead are siblings of
 * this rather than children, so they stay where they are: a column is a moment
 * in time, and scrolling up and down does not change the time.
 *
 * Left unpositioned deliberately — the playhead measures its offset against the
 * block's body, and a positioned scroller would put itself in between. */
function Window ({ rows, visible, cell, children }) {
	const seen = useRef(null);
	const windowed = Boolean(visible && visible < rows);

	/* Where the window sits on what it is looking at, as two fractions. */
	const [view, setView] = useState({ from: 0, span: 1 });

	const measure = useCallback(() => {
		const box = seen.current;

		if (!box || !box.scrollHeight) return;

		setView({
			from: box.scrollTop / box.scrollHeight,
			span: box.clientHeight / box.scrollHeight,
		});
	}, []);

	useEffect(() => {
		/* Opened at the bottom, which on a grid drawn high to low is the lowest
		   notes — where a bass line lives. */
		if (windowed && seen.current) seen.current.scrollTop = seen.current.scrollHeight;

		measure();
	}, [windowed, rows, cell, measure]);

	/* The strip is the thing you take hold of, not just the thing that reports.
	 * A finger landing anywhere on it brings that part of the pattern to the
	 * middle of the window, and keeps following while it moves. */
	const pushing = useRef(null);

	const push = (event) => {
		const box = seen.current;

		if (!box) return;

		const strip = event.currentTarget.getBoundingClientRect();
		const part = (event.clientY - strip.top) / strip.height;

		box.scrollTop = part * box.scrollHeight - box.clientHeight / 2;
	};

	const take = (event) => {
		event.preventDefault();
		event.currentTarget.setPointerCapture(event.pointerId);
		pushing.current = event.pointerId;
		push(event);
	};

	const carry = (event) => {
		if (pushing.current === event.pointerId) push(event);
	};

	const drop = (event) => {
		if (pushing.current === event.pointerId) pushing.current = null;
	};

	return html`
		<div class=${`window ${windowed ? "windowed" : ""}`}>
			<div
				class="scroller"
				ref=${seen}
				onScroll=${measure}
				style=${windowed ? { maxHeight: `${visible * (cell + GAP)}px`, overflowY: "auto" } : null}
			>${children}</div>

			${windowed && html`
				<div
					class="track"
					onPointerDown=${take}
					onPointerMove=${carry}
					onPointerUp=${drop}
					onPointerCancel=${drop}
				>
					<i style=${{
						top: `${view.from * 100}%`,
						height: `${Math.max(8, view.span * 100)}%`,
					}}></i>
				</div>`}
		</div>`;
}

function Grid ({ control, rows, steps, cells, visible, cell, pending, failed, onTap }) {
	/* A label column bounded by the viewport, then one column per step at
	   whatever size is set. The columns are that size exactly rather than at
	   least it: a person who asks for compact cells wants the space back for
	   something else, not the same grid stretched to fill the glass again. */
	const style = {
		gridTemplateColumns: `var(--label) repeat(${steps}, var(--cell))`,
	};

	return html`
		<${Window} rows=${rows.length} visible=${visible} cell=${cell}>
		<div class="grid" style=${style}>
			${rows.map((row) => html`
				<div class="row-label" key=${`label-${row}`}>${row.replace(/_/g, " ")}</div>
				${Array.from({ length: steps }, (_, step) => {
					const path = `${control}/${row}/${step}`;
					const on = (cells[row] || []).includes(step);

					return html`
						<div
							key=${path}
							data-path=${path}
							class=${["cell", on ? "on" : "", pending.has(path) ? "pending" : "",
								failed.has(path) ? "failed" : "",
								step % 4 === 0 ? "downbeat" : ""].filter(Boolean).join(" ")}
							onPointerDown=${(event) => { event.preventDefault(); onTap(path, !on); }}
						></div>`;
				})}
			`)}
		</div>
		<//>`;
}

/* A pitched pattern: one row per note, and a cell that is a note.
 *
 * A note is drawn as a bar reaching rightwards from where it starts, which is
 * how every piano roll draws one and needs no explaining. Position is pitch, so
 * the line is read as a shape before any label is read.
 *
 * Two gestures, both acting on the finger landing (#2046). Pressing an empty
 * cell places a note and begins sizing it: drag right and the note grows a step
 * at a time, each length sent as its own absolute set, so the bar on the glass
 * is never longer than the sequencer has agreed to. Pressing a note takes it
 * away. Resizing a note that is already there means drawing it again, which is
 * the first thing to revisit once this has been played.
 */
function NoteGrid ({ control, name, rows, steps, notes, cell, window: windowRows,
                    pending, failed, onSet }) {
	const style = {
		gridTemplateColumns: `var(--label) repeat(${steps}, var(--cell))`,
	};

	const drawing = useRef(null);

	const pitch = cell + GAP;

	const begin = (event, row, step, existing) => {
		event.preventDefault();

		if (existing) { onSet(`${name}/${row}/${step}`, false); return; }

		onSet(`${name}/${row}/${step}`, true);

		event.currentTarget.setPointerCapture(event.pointerId);
		drawing.current = { pointer: event.pointerId, row, step, from: event.clientX, length: 1 };
	};

	const stretch = (event) => {
		const drawn = drawing.current;

		if (!drawn || drawn.pointer !== event.pointerId) return;

		const wanted = Math.max(1, Math.min(
			steps - drawn.step, 1 + Math.round((event.clientX - drawn.from) / pitch)));

		if (wanted === drawn.length) return;

		drawn.length = wanted;
		onSet(`${name}/${drawn.row}/${drawn.step}/length`, wanted);
	};

	const finish = (event) => {
		if (drawing.current && drawing.current.pointer === event.pointerId) drawing.current = null;
	};

	return html`
		<${Window} rows=${rows.length} visible=${windowRows} cell=${cell}>
		<div class="grid notes" style=${style}>
			${rows.map((row) => html`
				<div class="row-label" key=${`label-${row}`}>${row}</div>
				${Array.from({ length: steps }, (_, step) => {
					const path = `${name}/${row}/${step}`;
					const note = (notes[row] || {})[String(step)];

					return html`
						<div
							key=${path}
							data-path=${path}
							class=${["cell", note ? "on" : "", pending.has(path) ? "pending" : "",
								failed.has(path) ? "failed" : "",
								step % 4 === 0 ? "downbeat" : ""].filter(Boolean).join(" ")}
							onPointerDown=${(event) => begin(event, row, step, Boolean(note))}
							onPointerMove=${stretch}
							onPointerUp=${finish}
							onPointerCancel=${finish}
						>${note && html`
							<div class="note" style=${{
								width: `${(note.length || 1) * pitch - GAP}px`,
							}}></div>`}</div>`;
				})}
			`)}
		</div>
		<//>`;
}

/* How hard each note is struck.
 *
 * A lane rather than a dial on every step: a dial small enough to fit a step is
 * too small to hit, and one shared dial would need a step selected first. A
 * lane shows the whole dynamic shape at once, which is the thing worth seeing.
 *
 * It edits the note in that column and does nothing where there is none —
 * a velocity with no note is not a state the sequencer could report. */
function VelocityLane ({ name, rows, steps, notes, range, cell, onSet }) {
	const style = {
		gridTemplateColumns: `var(--label) repeat(${steps}, var(--cell))`,
		height: `${LANE_CELLS * cell + (LANE_CELLS - 1) * GAP}px`,
	};

	const [low, high] = range || [1, 127];
	const holding = useRef(null);

	const at = (step) => {
		for (const row of rows) {
			const note = (notes[row] || {})[String(step)];

			if (note) return { row, note };
		}

		return null;
	};

	const set = (event, step) => {
		const found = at(step);

		if (!found) return;

		const box = event.currentTarget.getBoundingClientRect();
		const part = 1 - Math.min(1, Math.max(0, (event.clientY - box.top) / box.height));
		const wanted = Math.round(low + part * (high - low));

		if (wanted === found.note.velocity) return;

		onSet(`${name}/${found.row}/${step}/velocity`, wanted);
	};

	return html`
		<div class="lane" style=${style}>
			<div class="row-label">velocity</div>
			${Array.from({ length: steps }, (_, step) => {
				const found = at(step);
				const height = found ? Math.max(4, ((found.note.velocity - low) / (high - low)) * 100) : 0;

				return html`
					<div
						key=${`vel-${step}`}
						data-velocity=${step}
						class=${`bar ${step % 4 === 0 ? "downbeat" : ""}`}
						onPointerDown=${(event) => {
							event.preventDefault();
							event.currentTarget.setPointerCapture(event.pointerId);
							holding.current = event.pointerId;
							set(event, step);
						}}
						onPointerMove=${(event) => { if (holding.current === event.pointerId) set(event, step); }}
						onPointerUp=${() => { holding.current = null; }}
						onPointerCancel=${() => { holding.current = null; }}
					>${found && html`<i style=${{ height: `${height}%` }}></i>`}</div>`;
			})}
		</div>`;
}

/* An instrument's own settings: switches, numbers and choices.
 *
 * Three shapes cover every control-change message a Minitaur answers to, and
 * most likely most instruments (#2081). Nothing here knows that any of them is
 * a MIDI message — a panel draws a switch, and what that switch is wired to is
 * the composition's business.
 *
 * The ones worth glass are the parameters an instrument has no knob for at
 * all, which is why this is a block of its own rather than a strip beside a
 * grid: it is the part of the instrument the panel is the only way to reach. */
/* A step for a number the app declared none for.
 *
 * An absent step is itself the signal: the app sends one only where the type
 * implies it, so no step means a continuous value however round the number
 * standing in it happens to look. Reading it off the held value instead was
 * wrong in exactly the case that matters — `probability` runs 0 to 1 and
 * defaults to 1.0, which crosses the wire as 1, so the slider offered nothing
 * between none and all.
 *
 * Given two ends, a hundred or so positions across them is fine enough for a
 * finger and lands on figures a person can read back. With no ends there is
 * nothing to divide, so a tenth it is. */
const stepOf = (field) => {
	if (field.step !== undefined) return field.step;

	if (field.min !== undefined && field.max !== undefined) {
		return Math.max(1e-6, 10 ** Math.floor(Math.log10((field.max - field.min) / 100)));
	}

	return 0.1;
};

/* Binary floating point makes 0.1 + 0.2 into something no one wants to read on
 * a control surface. Six places is far finer than any parameter here. */
const tidy = (value) => Number(value.toFixed(6));

/* One parameter, in whichever of the four shapes it comes in.
 *
 * Shared between an instrument's settings and a generator's, because they are
 * the same shapes and two copies would drift apart the first time one of them
 * gained a kind (#2085).
 *
 * A number is a slider when the app or the composition said what its ends are,
 * and a stepper when nobody did. That is not a fallback so much as the ordinary
 * case: most of a generator's numbers have no natural bound — a duration in
 * beats, a spacing — and a slider with invented ends would be a lie a finger
 * could act on. A stepper works with one finger and no keyboard either way. */
function Setting ({ field, held, onSet }) {
	const sliding = useRef(null);

	/* Asked for whatever this parameter turns out to be, because a hook must
	   be: only a long choice opens a menu, and the shape is not known here
	   until after the hooks have run. */
	const [open, setOpen] = useState(false);
	const [where, setWhere] = useState(null);
	const trigger = useRef(null);

	/* A menu is placed against the viewport rather than against the button it
	   hangs from, and measured on the way open.
	
	   It has to escape its block: a part clips its own body so the playhead
	   cannot widen the page, and a menu inside that block is clipped by the
	   same rule — ten drum voices in a short block lost their lower half, which
	   is not a thing a person can scroll to because the block is what is
	   cutting them off. Nothing between here and the viewport establishes a
	   containing block, so `fixed` really does escape.
	
	   It opens upward when there is more room above, which is the ordinary case
	   for a parameter near the foot of the glass. */
	const show = () => {
		const box = trigger.current.getBoundingClientRect();
		const below = window.innerHeight - box.bottom - 16;
		const above = box.top - 16;

		setWhere({
			left: Math.round(box.left),
			minWidth: Math.round(box.width),
			...(below < 200 && above > below
				? { bottom: Math.round(window.innerHeight - box.top + 4), maxHeight: Math.round(above) }
				: { top: Math.round(box.bottom + 4), maxHeight: Math.round(below) }),
		});

		setOpen(true);
	};
	const bounded = field.min !== undefined && field.max !== undefined;

	const at = (event, box) =>
		Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));

	const along = (part) => {
		const step = stepOf(field);

		return tidy(Math.round((field.min + part * (field.max - field.min)) / step) * step);
	};

	const slide = (event) => {
		const wanted = along(at(event, event.currentTarget.getBoundingClientRect()));

		if (wanted !== held) onSet(wanted);
	};

	/* What the finger took hold of, decided once on the way down and then kept:
	   deciding it again on every move would swap ends under the finger the
	   moment the two crossed.
	
	   Three things it can be. An end, which moves alone. Or the span between
	   them, which moves both and keeps its width — a velocity of 30 to 50 is a
	   *character*, and wanting all of it louder is a different request from
	   wanting it wider. The span is only there to be taken hold of when the two
	   ends are actually apart; with both together there is no middle, so the
	   nearer end answers and the common default behaves as it always did. */
	const grip = (event) => {
		const box = event.currentTarget.getBoundingClientRect();
		const wanted = field.min + at(event, box) * (field.max - field.min);
		const [low, high] = held || [field.min, field.min];

		return (low < high && wanted > low && wanted < high)
			? { part: "span", from: wanted - low }
			: { part: Math.abs(wanted - low) <= Math.abs(wanted - high) ? "low" : "high" };
	};

	const slideRange = (event) => {
		const taken = sliding.current;

		if (!taken) return;

		const wanted = along(at(event, event.currentTarget.getBoundingClientRect()));
		const [low, high] = held || [field.min, field.min];
		let next;

		if (taken.part === "span") {
			const width = high - low;
			const start = Math.min(Math.max(wanted - taken.from, field.min), field.max - width);
			const settled = along((start - field.min) / (field.max - field.min));

			next = [settled, tidy(settled + width)];

		} else if (taken.part === "low") {
			next = [Math.min(wanted, high), high];

		} else {
			next = [low, Math.max(wanted, low)];
		}

		if (next[0] !== low || next[1] !== high) onSet(next);
	};

	const stepper = (value, onChange) => html`
		<div class="stepper">
			<button onPointerDown=${(event) => {
				event.preventDefault();
				onChange(tidy((value ?? 0) - stepOf(field)));
			}}>−</button>
			<span>${value ?? 0}</span>
			<button onPointerDown=${(event) => {
				event.preventDefault();
				onChange(tidy((value ?? 0) + stepOf(field)));
			}}>+</button>
		</div>`;

	if (field.kind === "switch") {
		return html`
			<button
				class=${`switch ${held ? "on" : ""}`}
				onPointerDown=${(event) => { event.preventDefault(); onSet(!held); }}
			>${held ? "on" : "off"}</button>`;
	}

	if (field.kind === "choice") {
		const options = field.options || [];

		/* Laid out flat while there are few enough to take in at a glance, and
		   behind a menu when there are not. A row of buttons is a good way to
		   choose one of three and a poor way to choose one of ten: it says
		   "several of these" while accepting only one, and it costs the height
		   of three rows to say it. The line is drawn at four because that is
		   where an instrument's settings sit — glide type, note priority — and
		   a generator's vocabularies do not: bias has eight, a drum kit ten.
		
		   The menu is the one the size chooser already uses, rather than a
		   second way of doing the same thing. */
		if (options.length <= CHOICE_BUTTONS) {
			return html`
				<div class="choices">
					${options.map((option) => html`
						<button
							key=${option.value}
							class=${option.value === held ? "here" : ""}
							onPointerDown=${(event) => { event.preventDefault(); onSet(option.value); }}
						>${option.label || option.value}</button>`)}
				</div>`;
		}

		const chosen = options.find((option) => option.value === held);

		return html`
			<div class="menu">
				<button
					ref=${trigger}
					class=${open ? "open" : ""}
					onPointerDown=${(event) => {
						event.preventDefault();
						open ? setOpen(false) : show();
					}}
				>${chosen ? chosen.label || chosen.value : "choose"}<i>▾</i></button>

				${open && where && html`
					<div
						class="options"
						style=${{
							left: `${where.left}px`,
							minWidth: `${where.minWidth}px`,
							maxHeight: `${where.maxHeight}px`,
							...(where.top !== undefined
								? { top: `${where.top}px` }
								: { bottom: `${where.bottom}px` }),
						}}
					>
						${options.map((option) => html`
							<button
								key=${option.value}
								class=${option.value === held ? "here" : ""}
								onPointerDown=${(event) => {
									event.preventDefault();
									onSet(option.value);
									setOpen(false);
								}}
							>${option.label || option.value}</button>`)}
					</div>`}
			</div>`;
	}

	if (field.kind === "range") {
		const [low, high] = held || [field.min ?? 0, field.min ?? 0];

		if (!bounded) {
			return html`
				<div class="pair">
					${stepper(low, (value) => onSet([Math.min(value, high), high]))}
					${stepper(high, (value) => onSet([low, Math.max(value, low)]))}
				</div>`;
		}

		const span = field.max - field.min;
		const place = (value) => `${((value - field.min) / span) * 100}%`;

		return html`
			<div
				class="dial ranged"
				onPointerDown=${(event) => {
					event.preventDefault();
					event.currentTarget.setPointerCapture(event.pointerId);

					sliding.current = grip(event);
					slideRange(event);
				}}
				onPointerMove=${(event) => {
					if (sliding.current) slideRange(event);
				}}
				onPointerUp=${() => { sliding.current = null; }}
				onPointerCancel=${() => { sliding.current = null; }}
			>
				<i style=${{ left: place(low), width: `${((high - low) / span) * 100}%` }}></i>
				<b style=${{ left: place(low) }}></b>
				<b style=${{ left: place(high) }}></b>
				<span>${low} – ${high}</span>
			</div>`;
	}

	if (!bounded) return stepper(held, (value) => onSet(value));

	return html`
		<div
			class="dial"
			onPointerDown=${(event) => {
				event.preventDefault();
				event.currentTarget.setPointerCapture(event.pointerId);
				sliding.current = event.pointerId;
				slide(event);
			}}
			onPointerMove=${(event) => {
				if (sliding.current === event.pointerId) slide(event);
			}}
			onPointerUp=${() => { sliding.current = null; }}
			onPointerCancel=${() => { sliding.current = null; }}
		>
			<i style=${{ width: `${((held - field.min) / (field.max - field.min)) * 100}%` }}></i>
			<span>${held}</span>
		</div>`;
}

function Params ({ name, fields, values, cell, onSet }) {
	const style = {
		gridTemplateColumns: `var(--label) repeat(${PARAM_CELLS}, var(--cell))`,
	};

	return html`
		<div class="grid params" style=${style}>
			${fields.map((field) => [
				html`
					<div class="row-label" key=${`label-${field.name}`}>
						${field.label || field.name}
					</div>`,
				html`
					<div class="setting" key=${field.name}
						style=${{ gridColumn: `span ${PARAM_CELLS}` }}>
						<${Setting} field=${field} held=${values[field.name]}
							onSet=${(value) => onSet(`${name}/${field.name}`, value)} />
					</div>`,
			]).flat()}
		</div>`;
}


/* One contribution: a single generator, the parameters it takes, and where it
 * sits in the stack that builds a pattern.
 *
 * A window of its own rather than a row in a tall block, which is what Simon
 * asked for after building a stack of two: "generators should each appear in
 * their own window ... generator windows can move freely, as with pattern
 * windows" (#2109). Two contributions are two things, and two things a person
 * arranges themselves are two things they can find again.
 *
 * The order is musical content rather than presentation: a fill told to skip
 * where a note already sits depends entirely on what ran before it, so moving a
 * layer up or down changes what is heard. Free-floating windows lose the one
 * thing a stack showed for nothing — which of them runs first — so the arrows
 * stay and the place in the stack is written beside them.
 *
 * Nothing here knows the name of a single generator. The list comes from the
 * app describing itself, joined by the composition to the voices this studio
 * has (#2085), and this draws whatever arrives — which is the same rule that
 * keeps drum voices and control-change numbers out of the package.
 *
 * A whole stack is sent for anything that changes the list — adding, removing,
 * bypassing, reordering — and a single parameter is sent on its own. The split
 * is what lets two people turn different knobs without overwriting each other,
 * while a structural change genuinely is about the list. */
function Contribution ({ name, layer, layers, offered, onSet }) {
	const style = {
		gridTemplateColumns: `var(--label) repeat(${PARAM_CELLS}, var(--cell))`,
	};

	const full = { gridColumn: `span ${PARAM_CELLS + 1}` };
	const index = layers.findIndex((one) => one.id === layer.id);
	const send = (next) => onSet(`${name}/layers`, next);

	const shift = (by) => {
		const to = index + by;

		if (index < 0 || to < 0 || to >= layers.length) return;

		const next = [...layers];

		[next[index], next[to]] = [next[to], next[index]];
		send(next);
	};

	const press = (act) => (event) => { event.preventDefault(); act(); };

	return html`
		<div class="recipe">
			<div class="grid params" style=${style}>
				<div class="layer" style=${full}>
					<button
						class=${`switch ${layer.bypassed ? "" : "on"}`}
						title="bypass"
						onPointerDown=${press(() => send(layers.map((one) =>
							one.id === layer.id ? { ...one, bypassed: !one.bypassed } : one)))}
					>${layer.bypassed ? "off" : "on"}</button>
					${/* Which of them runs first, said in words because the windows no
					     longer say it by sitting on top of one another. Left off when
					     there is only one, where it would be noise. */ ""}
					${layers.length > 1 && html`
						<span class="place">${index + 1} of ${layers.length}</span>`}
					<span class="spacer"></span>
					<button
						class="move" disabled=${index <= 0}
						onPointerDown=${press(() => shift(-1))}
					>↑</button>
					<button
						class="move" disabled=${index < 0 || index === layers.length - 1}
						onPointerDown=${press(() => shift(1))}
					>↓</button>
					<button
						class="drop" title="remove this layer"
						onPointerDown=${press(() => send(layers.filter((one) => one.id !== layer.id)))}
					>✕</button>
				</div>

				${offered
					? offered.parameters.map((field) => [
						html`
							<div class="row-label" key=${`label-${field.name}`}>
								${field.label || field.name}
							</div>`,
						html`
							<div class="setting" key=${field.name}
								style=${{ gridColumn: `span ${PARAM_CELLS}` }}>
								<${Setting}
									field=${field}
									held=${(layer.params || {})[field.name]}
									onSet=${(value) => onSet(`${name}/${layer.id}/${field.name}`, value)} />
							</div>`,
					]).flat()
					: html`
						<div class="unsupported" style=${full}>
							The application no longer offers a generator called
							<b>${layer.generator}</b>. This layer is not playing, and
							removing it is the only thing that will change that.
						</div>`}
			</div>
		</div>`;
}


/* A stack whose pattern is not on this page, reduced to the one thing it still
 * has to offer.
 *
 * "Add a generator" belongs on the pattern, which is where Simon put it — but a
 * page carrying the stack without the pattern is an ordinary thing to make, and
 * on one of those there would otherwise be no way to add anything at all. So
 * the stack keeps a small window of its own, and only there. */
function Orphan ({ builds }) {
	return html`
		<div class="orphan">
			Building <b>${builds ? builds.replace(/_/g, " ") : "a pattern"}</b>, which is
			not on this page.
		</div>`;
}


/* A sheet: the whole glass, briefly, for something that needs answering.
 *
 * Used for the two things that do. Picking a generator out of thirty-three is a
 * list, not a dropdown, and on a hand-held panel a dropdown of that length is
 * worse than the screen. Clearing a pattern is destructive and has no undo, so
 * it has to be read before it is agreed to — which is the whole argument for a
 * dialog over an armed button: only a dialog can say *what* is about to go. */
function Sheet ({ title, onClose, children }) {
	return html`
		<div
			class="sheet"
			onPointerDown=${(event) => {
				if (event.target === event.currentTarget) { event.preventDefault(); onClose(); }
			}}
		>
			<div class="sheet-body">
				<header>
					<b>${title}</b>
					<span class="spacer"></span>
					<button
						onPointerDown=${(event) => { event.preventDefault(); onClose(); }}
					>close</button>
				</header>
				${children}
			</div>
		</div>`;
}

/* What a pattern can be asked to do, beside the grid rather than inside it.
 *
 * The title bar is the handle and has to stay one, so this is the place where
 * a pattern's own actions accrue — Simon's words, and clear is already the
 * second of them. */
function Footer ({ onAdd, onClear }) {
	if (!onAdd && !onClear) return null;

	return html`
		<footer class="part-foot">
			${onAdd && html`
				<button
					class="offer add"
					onPointerDown=${(event) => { event.preventDefault(); onAdd(); }}
				>add a generator</button>`}
			<span class="spacer"></span>
			${onClear && html`
				<button
					class="clear"
					onPointerDown=${(event) => { event.preventDefault(); onClear(); }}
				>clear</button>`}
		</footer>`;
}


/* One part: a titled block holding one control.
 *
 * The title comes from the app, never from here (#2071). Superintendent does
 * not know that a grid is a drum pattern or that a row is a voice, and a title
 * invented here would be the one place a rig's names leaked into the package.
 * An app that offers none gets its address tidied up, which is honest about
 * where the words came from.
 *
 * The bar is also the handle. A step grid is tappable over its whole face, so
 * there is nowhere on it to take hold of that is not a control; the title is
 * the surface that is not one. */
function Part ({ title, name, at, cell, depth, locked, onMove, onRaise, onHold, onSettled, onTouch, footer, children }) {
	const pitch = cell + GAP;
	const held = useRef(null);

	const place = {
		left: `${(at ? at.x : 0) * pitch}px`,
		top: `${(at ? at.y : 0) * pitch}px`,
		zIndex: depth,
	};

	/* Taking hold. The pointer is captured so the block keeps following the
	   finger even when the finger leaves it, which it will: a block dragged
	   quickly is always behind the hand for a frame. */
	const grab = (event) => {
		if (locked) return;

		event.preventDefault();
		event.currentTarget.setPointerCapture(event.pointerId);

		held.current = {
			pointer: event.pointerId,
			fromX: event.clientX, fromY: event.clientY,
			x: at ? at.x : 0, y: at ? at.y : 0,
		};

		onRaise(name);
		onHold(true);
	};

	/* A cell at a time, measured from where the finger started rather than
	   from where it was last frame, so a slow drag cannot accumulate rounding
	   into a drift. Nothing is refused and nothing is displaced: every square
	   is a legal square, and a block may sit on top of another (#2078). */
	const move = (event) => {
		const from = held.current;

		if (!from || from.pointer !== event.pointerId) return;

		const x = Math.max(0, from.x + Math.round((event.clientX - from.fromX) / pitch));
		const y = Math.max(0, from.y + Math.round((event.clientY - from.fromY) / pitch));

		if (!at || x !== at.x || y !== at.y) {
			from.moved = true;
			onMove(name, x, y);
		}
	};

	/* Kept on the way up rather than on leaving a mode, because there is no
	   longer a mode to leave. Same guarantee as before and finer: a drag in
	   motion is never half-saved, and an accidental nudge is one write rather
	   than twenty (#2075). */
	const release = (event) => {
		if (!held.current || held.current.pointer !== event.pointerId) return;

		const moved = held.current.moved;

		held.current = null;
		onHold(false);

		if (moved) onSettled();
	};

	return html`
		<section
			class="part" data-part=${name} style=${place}
			${/* Anywhere on the block, not only its handle: a person turning a knob
			     on a generator is asking the same question a person dragging it is
			     — what does this feed? — so the same line brightens (#2109). It is
			     let go of at the document, which is the only listener a pointer
			     captured by a slider cannot slip past. */ ""}
			onPointerDown=${() => onTouch(name)}
		>
			<header
				class="part-title"
				onPointerDown=${grab}
				onPointerMove=${move}
				onPointerUp=${release}
				onPointerCancel=${release}
			>${title || name.replace(/_/g, " ")}</header>
			<div class="part-body">${children}</div>
			${footer}
		</section>`;
}

/* The four points a line may leave a block by: the middle of each of its sides.
 *
 * Corners are deliberately not offered. A line from a corner reads as pointing
 * past the block rather than at it, and the whole job of these lines is to say
 * which two things belong together. */
function sidesOf (box) {
	return [
		{ x: box.x + box.w / 2, y: box.y },
		{ x: box.x + box.w, y: box.y + box.h / 2 },
		{ x: box.x + box.w / 2, y: box.y + box.h },
		{ x: box.x, y: box.y + box.h / 2 },
	];
}

/* The lines joining each contribution to the pattern it feeds.
 *
 * Simon asked for this in the same breath as the windows, and the two are one
 * feature: the moment a stack becomes several blocks that move freely, nothing
 * on the glass says which pattern any of them builds. "A line should be drawn
 * connecting the two closest sides of the generator window and its associated
 * pattern" (#2109).
 *
 * **The line carries a direction, and does so now.** Only one direction exists
 * today — a contribution feeds a pattern — but Simon has already named the case
 * that needs the other one: an element that *shows* a property of a pattern
 * rather than controlling it. An arrowhead costs a triangle today and a format
 * change later, so it is drawn from the start. The direction is the ordering:
 * the head is always at ``to``.
 *
 * Measured from the page rather than worked out from the lattice. A block's
 * height depends on what is in it — a generator with two parameters is shorter
 * than one with five — and the only thing that reliably knows a rendered height
 * is the rendering. That also means this cannot drift from the fit: it is not a
 * second opinion about geometry, it is the geometry.
 *
 * It takes no pointer events at all, so a line drawn across a grid cannot cost
 * a tap. */
function Connections ({ box, joins, touched, when }) {
	const [drawn, setDrawn] = useState([]);

	useLayoutEffect(() => {
		const wrap = box.current;

		if (!wrap || !joins.length) { setDrawn((was) => (was.length ? [] : was)); return; }

		const measure = () => {
			const outer = wrap.getBoundingClientRect();
			const where = new Map();

			for (const part of wrap.querySelectorAll("[data-part]")) {
				const at = part.getBoundingClientRect();

				/* Relative to the scrolled content rather than to the viewport,
				   because that is the space the blocks themselves are placed
				   in. A line has to stay on its block when the page scrolls. */
				where.set(part.dataset.part, {
					x: at.left - outer.left + wrap.scrollLeft,
					y: at.top - outer.top + wrap.scrollTop,
					w: at.width, h: at.height,
				});
			}

			const next = [];

			for (const join of joins) {
				const from = where.get(join.from);
				const to = where.get(join.to);

				if (!from || !to) continue;

				let best = null;

				for (const a of sidesOf(from)) {
					for (const b of sidesOf(to)) {
						const away = Math.hypot(b.x - a.x, b.y - a.y);

						if (!best || away < best.away) best = { a, b, away };
					}
				}

				next.push({ ...join, a: best.a, b: best.b });
			}

			/* Compared before it is kept. This runs from an observer as well as
			   from the effect, and a fresh array every time would re-render the
			   overlay for every resize of every block. */
			setDrawn((was) => (JSON.stringify(was) === JSON.stringify(next) ? was : next));
		};

		measure();

		/* A block that is dragged moves without changing size, and a block that
		   is resized changes size without being told: the first arrives as a new
		   layout in `when`, and the second only ever arrives here. Both have to
		   be watched — a line that followed one and not the other would come
		   adrift from the block it names, which is worse than no line. */
		const watcher = new ResizeObserver(measure);

		watcher.observe(wrap);

		for (const part of wrap.querySelectorAll("[data-part]")) watcher.observe(part);

		return () => watcher.disconnect();
	}, [when]);

	if (!drawn.length) return null;

	/* Large enough to hold every line and no larger. Every endpoint sits on the
	   edge of a block, so this can never be wider than the blocks already are —
	   which matters, because an overlay that outgrew them would scroll the page
	   to somewhere there is nothing to see. */
	const extent = drawn.reduce(
		(most, line) => ({
			x: Math.max(most.x, line.a.x, line.b.x),
			y: Math.max(most.y, line.a.y, line.b.y),
		}),
		{ x: 0, y: 0 });

	return html`
		<svg class="joins" width=${Math.ceil(extent.x) + 1} height=${Math.ceil(extent.y) + 1}>
			${drawn.map((line) => {
				const angle = Math.atan2(line.b.y - line.a.y, line.b.x - line.a.x);
				const back = {
					x: line.b.x - Math.cos(angle) * ARROW,
					y: line.b.y - Math.sin(angle) * ARROW,
				};
				const wing = ARROW * 0.42;
				const head = [
					`M ${line.b.x} ${line.b.y}`,
					`L ${back.x - Math.sin(angle) * wing} ${back.y + Math.cos(angle) * wing}`,
					`L ${back.x + Math.sin(angle) * wing} ${back.y - Math.cos(angle) * wing}`,
					"Z",
				].join(" ");

				const live = touched === line.from || touched === line.to;

				return html`
					<g key=${`${line.from}>${line.to}`}
						class=${`join ${live ? "live" : ""}`} data-join=${`${line.from}>${line.to}`}>
						<line x1=${line.a.x} y1=${line.a.y} x2=${line.b.x} y2=${line.b.y} />
						<path d=${head} />
					</g>`;
			})}
		</svg>`;
}


/* The parts on this page, by name, while it is being arranged.
 *
 * Overlap is what makes this necessary rather than convenient. A block can be
 * covered completely, and the only way to take hold of one is its title bar,
 * so without a list there would be no way back to it. Choosing a name raises
 * that block to the top, which is the same gesture that a drag performs and
 * therefore needs no explaining. */
function Inventory ({ names, titles, onRaise }) {
	if (names.length < 2) return null;

	return html`
		<div class="inventory">
			${names.map((name) => html`
				<button
					key=${name}
					onPointerDown=${(event) => { event.preventDefault(); onRaise(name); }}
				>${titles[name] || name.replace(/_/g, " ")}</button>`)}
		</div>`;
}

/* The highlight tracking what is sounding.
 *
 * The sequencer reports beats, not steps: between two of them the position is
 * worked out here, so the highlight moves smoothly instead of hopping four
 * times a bar. It is moved by transform alone, which keeps it off the layout
 * path — the grid itself is never re-laid-out to animate it. */
function Playhead ({ anchor, steps, beats, paused }) {
	const bar = useRef(null);

	/* The latest beat, held rather than depended on. Listing the anchor among
	   the effect's dependencies cancelled the animation and started another
	   twice a second, which was harmless with one playhead on a page and is
	   not what should happen now that a page carries several. */
	const from = useRef(anchor);

	useEffect(() => { from.current = anchor; }, [anchor]);

	/* How long the clock has been held, and since when.
	 *
	 * A held transport sends no beats, so extrapolation would run on without
	 * anything to correct it: the highlight would drift up to a whole beat
	 * forward, stop at the clamp, and snap back when play resumed. Holding the
	 * clock has to hold this too. The moment the pause is confirmed is where
	 * the sequencer stopped, so that is where the highlight stays, and the time
	 * spent held is subtracted afterwards so resuming continues rather than
	 * jumps. The next beat clears the sum and makes it exact again. */
	const heldSince = useRef(null);
	const held = useRef(0);

	useEffect(() => {
		if (paused) {
			if (heldSince.current === null) heldSince.current = performance.now();
			return;
		}

		if (heldSince.current !== null) {
			held.current += performance.now() - heldSince.current;
			heldSince.current = null;
		}
	}, [paused]);

	/* A beat is a fresh reading of where the sequencer actually is, so whatever
	   was being carried to correct for a hold has just been made irrelevant. */
	useEffect(() => { held.current = 0; }, [anchor]);

	useEffect(() => {
		if (!bar.current) return;

		let frame;
		const grid = bar.current.parentElement.querySelector(".grid");

		const move = () => {
			const anchor = from.current;
			const first = grid && grid.children[1];
			const second = grid && grid.children[2];

			if (first && anchor && anchor.interval) {
				const reading = heldSince.current === null ? performance.now() : heldSince.current;
				const elapsed = Math.max(0, reading - anchor.at - held.current) / 1000;
				const beatNow = anchor.beat + Math.min(elapsed / anchor.interval, 1);
				const step = (beatNow * (steps / beats)) % steps;

				/* Both numbers are read off the grid rather than assumed. The
				   pitch is the distance between two cells, which is a cell and
				   a gap however either is currently sized. */
				const width = first.getBoundingClientRect().width;
				const pitch = second ? second.offsetLeft - first.offsetLeft : width;

				/* Two offsets, because there are two boxes between the cell and
				   this bar: the cell sits inside the grid, and the grid sits
				   inside the wrap's padding. Counting only the first left the
				   highlight a padding's width to the left of the step it was
				   marking. */
				const left = grid.offsetLeft + first.offsetLeft;

				bar.current.style.width = `${width}px`;
				bar.current.style.transform = `translateX(${left + step * pitch}px)`;
			}

			frame = requestAnimationFrame(move);
		};

		move();
		return () => cancelAnimationFrame(frame);
	}, [steps, beats]);

	return html`<div class="playhead" ref=${bar}></div>`;
}

/* Pause and tempo.
 *
 * Both faces show what the composition holds, never what was last tapped — the
 * same rule the cells follow. Pause keeps the composition's place: the clock
 * is held rather than stopped, so letting go continues from the same beat.
 *
 * A pause can be refused, silently, when the pulse is not Subsequence's to
 * hold — following an external clock, or in an Ableton Link session. The
 * refusal comes back as a nack and the button springs back with the reason,
 * because no confirming event will ever arrive. */
function Transport ({ control, name, fields, up, onSet }) {
	const paused = fields.paused === true;
	const bpm = fields.bpm;
	const [low, high] = control.tempo_range || [40, 240];
	const canPause = (control.fields || []).includes("paused");

	const nudge = (by) => {
		if (typeof bpm !== "number") return;
		onSet(`${name}/bpm`, Math.min(high, Math.max(low, Math.round((bpm + by) * 10) / 10)));
	};

	return html`
		<div class="transport">
			${canPause && html`
				<button
					class=${`hold ${paused ? "engaged" : ""}`}
					disabled=${!up}
					onPointerDown=${(event) => { event.preventDefault(); onSet(`${name}/paused`, !paused); }}
				>${paused ? "PLAY" : "PAUSE"}</button>`}

			<div class="tempo">
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(-5); }}>−5</button>
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(-1); }}>−1</button>
				<span class="reading">${typeof bpm === "number" ? bpm.toFixed(bpm % 1 ? 1 : 0) : "—"}<i>BPM</i></span>
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(1); }}>+1</button>
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(5); }}>+5</button>
			</div>
		</div>`;
}

/* Moving between the pages a composition offers.
 *
 * A row of buttons, one per page, drawn the way a step grid's own cells are —
 * Simon's suggestion, and it is right: a panel that has taught a hand to tap
 * cells in a row has already taught it this. Beyond a few pages a row stops
 * being readable at a glance, so it gives way to previous and next with the
 * place shown, which is the same navigation at a size that still fits.
 *
 * Nothing is drawn for a composition that offers one page or none. A control
 * with one choice is furniture. */
function Pages ({ pages, current, onChoose }) {
	if (pages.length < 2) return null;

	const at = Math.max(0, pages.findIndex((page) => page.id === current));
	const step = (by) => onChoose(pages[(at + by + pages.length) % pages.length].id);

	if (pages.length > PAGE_BUTTONS) {
		return html`
			<div class="pages">
				<button onPointerDown=${(e) => { e.preventDefault(); step(-1); }}>‹</button>
				<span class="which">${pages[at].title}<i>${at + 1}/${pages.length}</i></span>
				<button onPointerDown=${(e) => { e.preventDefault(); step(1); }}>›</button>
			</div>`;
	}

	return html`
		<div class="pages">
			${pages.map((page) => html`
				<button
					key=${page.id}
					class=${page.id === pages[at].id ? "here" : ""}
					onPointerDown=${(e) => { e.preventDefault(); onChoose(page.id); }}
				>${page.title}</button>`)}
		</div>`;
}

/* What is running, and whether it is the latest.
 *
 * The version answers "which release is this", and comes from the package
 * metadata, which is written when the package is installed rather than when it
 * runs — so on a source tree that has moved on it names the install and not the
 * files. The build is a hash of the page as it is on disk now, so it is the one
 * that can tell this browser it is behind. Both are shown, because the first is
 * what a person quotes and the second is what is true.
 *
 * A stale page is never reloaded automatically. Someone may be playing. */
function Build ({ service, stale }) {
	if (!service) return null;

	if (stale) {
		return html`
			<button class="reload" onPointerDown=${(event) => { event.preventDefault(); location.reload(); }}>
				newer page available — tap to load it
			</button>`;
	}

	const name = service.version ? `v${service.version}` : "unversioned";

	return html`<span class="build">${name}${service.build && html` · ${service.build}`}</span>`;
}

/* ------------------------------------------------------------------ */
/* How big a cell is                                                   */
/* ------------------------------------------------------------------ */

/* Where the parts sit, and how big a cell is — one question, not two.
 *
 * The lattice cell is the step cell (#2078). A part is placed at (x, y) in
 * those cells and nothing about its size is stored: its footprint follows its
 * contents at whatever size the person has set, so a pattern that gains steps
 * simply reaches further from the same corner. Every position is legal and
 * parts may overlap, which is what makes that safe — without it a part that
 * grew would demand a re-flow, and re-flowing somebody's layout behind their
 * back is exactly what #2072 refused.
 *
 * Steps line up between parts for free. Every block carries the same label
 * column and the same inset, and every position is a whole number of cells, so
 * step five of one pattern lands directly above step five of another.
 *
 * Returns the element to measure, the size in pixels, the choice behind it and
 * a way to change that choice. The choice is remembered on the panel, which is
 * the closest thing to per-person storage that exists while page files are
 * still unsettled (#1948) — one browser profile is one panel is, in practice,
 * one pair of hands. */

/* What a block measures, in pixels, at a given cell size.
 *
 * Everything scales with the cell except the parts that cannot: a block's
 * border and padding, which are constant, and the title bar, which has a
 * legibility floor. A block one cell taller than it looks at the smallest size
 * is a rounding error; a title nobody can read is not. */
function blockSize (block, cell, chrome) {
	const width = LABEL_CELLS * cell + (LABEL_CELLS - 1) * GAP
		+ GAP + block.steps * cell + (block.steps - 1) * GAP + chrome.x;

	/* Every row is one cell, a control's included. The fit and the stylesheet
	   read it from the same function so they cannot come to disagree. */
	const row = controlRow(cell);

	const height = Math.max(TITLE_FLOOR, cell)
		+ block.rows * row + (block.rows - 1) * GAP + chrome.y;

	return { width, height };
}

/* Where a part goes when nobody has placed it yet.
 *
 * Left to right and then down, which is the arrangement a person is least
 * surprised by before they have made one of their own. It is a starting point
 * and nothing more: the moment anything is dragged, this stops being consulted
 * for that part. */
function autoPlace (blocks, across) {
	const placed = {};

	let x = 0;
	let y = 0;
	let tallest = 0;

	for (const block of blocks) {
		/* A block's footprint in cells comes from what is in it: the label
		   column plus a cell per step across, a title plus a cell per row
		   down. Nothing measured, because nothing here needs pixels.
		
		   Plus a cell of air on each side. Blocks packed edge to edge read as
		   one surface with lines drawn on it; a lane between them says they are
		   separate things, which they are. A person who wants them touching can
		   drag them together, and this stops being consulted for that block the
		   moment they do. */
		const wide = LABEL_CELLS + block.steps + SEPARATION;
		const high = 1 + block.rows + SEPARATION;

		if (x && x + wide > across) { x = 0; y += tallest; tallest = 0; }

		placed[block.name] = { x, y };

		x += wide;
		tallest = Math.max(tallest, high);
	}

	return placed;
}

/* How many cells across a panel this wide would hold at the tested size.
 *
 * Deliberately not the current size. A starting arrangement worked out from
 * the size in force would move every time somebody changed that setting, and
 * an arrangement that rearranges itself is not one. */
function acrossAtTestedSize () {
	const tested = SIZES.find((size) => size.key === "tested").px;

	return Math.max(1, Math.floor(window.innerWidth / (tested + GAP)));
}

function useCellSize (blocks, layout, dragging) {
	const [choice, setChoice] = useState(() => {
		try {
			return localStorage.getItem(SIZE_KEY) || DEFAULT_SIZE;
		} catch (error) {
			/* Storage can be refused outright rather than merely empty. A panel
			   in that state works; it just forgets between reloads. */
			return DEFAULT_SIZE;
		}
	});

	const [cell, setCell] = useState(SIZES.find((size) => size.key === "tested").px);
	const wrap = useRef(null);

	/* The arrangement the fit is solving for, which is deliberately not the one
	   under the finger.
	 *
	 * Dragging a block changes the layout, and under "fit the glass" a larger
	 * arrangement answers by shrinking every cell — so a drag resized the whole
	 * page while it was still being made, by nearly half in one measurement.
	 * Simon settled the principle in #2072: a page that no longer fits scrolls,
	 * it does not rearrange or resize itself. So the fit uses the arrangement as
	 * it stood when the drag began, and catches up once when it ends, which
	 * is also when the arrangement is saved (#2075). */
	const solving = useRef(layout);

	if (!dragging) solving.current = layout;

	const choose = useCallback((key) => {
		setChoice(key);

		try {
			localStorage.setItem(SIZE_KEY, key);
		} catch (error) {
			/* As above: forgetting is the only consequence. */
		}
	}, []);

	useEffect(() => {
		/* A pinch does not land on one of the named steps, so a size may also be
		   a plain number of pixels. It is kept the same way and read back the
		   same way, which is why the chooser can go on showing what is set
		   without knowing where it came from. */
		const pinched = Number(choice);

		if (Number.isFinite(pinched) && pinched >= FIT_FLOOR) { setCell(pinched); return; }

		const named = SIZES.find((size) => size.key === choice);

		if (!named) { setChoice(DEFAULT_SIZE); return; }
		if (named.px) { setCell(named.px); return; }

		/* Fitting an arrangement cannot be divided out, because not everything
		   in it scales: a title bar has a floor and a block's border does not
		   move at all. So the largest cell that fits is searched for rather
		   than solved for — seven halvings of the range, each asking the same
		   plain question of a candidate size: does every part still land inside
		   the box? That also means the sum never has to be rewritten when
		   something new stops scaling. */
		const fit = () => {
			const box = wrap.current;

			if (!box || !blocks.length) return;

			const first = box.querySelector(".part");
			const inside = first && first.querySelector(".grid");
			const title = first && first.querySelector(".part-title");

			if (!first || !inside || !title) return;

			const outer = box.getBoundingClientRect();
			const shape = getComputedStyle(box);

			const room = {
				width: outer.width - parseFloat(shape.paddingLeft) - parseFloat(shape.paddingRight) - FIT_SLACK,
				height: outer.height - parseFloat(shape.paddingTop) - parseFloat(shape.paddingBottom) - FIT_SLACK,
			};

			/* The part of a block that does not scale, measured rather than
			   enumerated: what is left of it once the grid inside and the
			   title bar above are taken away. */
			const chrome = {
				x: first.getBoundingClientRect().width - inside.getBoundingClientRect().width,
				y: first.getBoundingClientRect().height - inside.getBoundingClientRect().height
					- title.getBoundingClientRect().height,
			};

			const fits = (candidate) => {
				const pitch = candidate + GAP;

				return blocks.every((block) => {
					const at = solving.current[block.name] || { x: 0, y: 0 };
					const size = blockSize(block, candidate, chrome);

					return at.x * pitch + size.width <= room.width
						&& at.y * pitch + size.height <= room.height;
				});
			};

			let low = FIT_FLOOR;
			let high = FIT_CEILING;

			if (!fits(low)) { setCell(FIT_FLOOR); return; }

			while (high - low > 1) {
				const middle = Math.floor((low + high) / 2);

				if (fits(middle)) low = middle; else high = middle;
			}

			setCell(low);
		};

		fit();

		/* The viewport is the input, so anything that changes it — a rotation,
		   a window resize, a browser leaving kiosk mode — has to be an input
		   too, rather than something only a reload would pick up. */
		const watcher = new ResizeObserver(fit);

		if (wrap.current) watcher.observe(wrap.current);

		return () => watcher.disconnect();
	}, [choice, JSON.stringify(blocks), dragging ? "held" : JSON.stringify(layout)]);

	/* Both written from here, so the stylesheet never has to work out a row
	   height of its own and then disagree with the fit about it. */
	useEffect(() => {
		document.documentElement.style.setProperty("--cell", `${cell}px`);
		document.documentElement.style.setProperty("--row", `${controlRow(cell)}px`);
	}, [cell]);

	return { wrap, cell, choice, choose };
}

/* Pinch to resize, so the size is reachable without finding the control for it.
 *
 * Simon asked for this after using a smaller screen: on a hand-held panel, being
 * able to spread two fingers to see one instrument closely and pinch back to see
 * every instrument is how a person expects to move around, and hunting for a
 * menu in the corner is not.
 *
 * It sets the panel's own cell size rather than the browser's zoom. Browser zoom
 * would scale the type and the touch targets together and leave the same amount
 * of music on the glass; this is the setting a person would otherwise have
 * chosen from the menu, so what comes into view is more of the piece.
 *
 * Nothing is captured and nothing is prevented until the gesture is certain, so
 * a two-finger chord on a grid is still two taps. */
function usePinch (cell, choose) {
	const held = useRef({ points: new Map(), apart: 0, from: 0, engaged: false });

	const down = useCallback((event) => {
		const gesture = held.current;

		gesture.points.set(event.pointerId, { x: event.clientX, y: event.clientY });

		if (gesture.points.size !== 2) return;

		const [one, two] = [...gesture.points.values()];

		gesture.apart = Math.hypot(one.x - two.x, one.y - two.y);
		gesture.from = cell;
		gesture.engaged = false;
	}, [cell]);

	const move = useCallback((event) => {
		const gesture = held.current;

		if (!gesture.points.has(event.pointerId)) return;

		gesture.points.set(event.pointerId, { x: event.clientX, y: event.clientY });

		if (gesture.points.size !== 2 || !gesture.apart) return;

		const [one, two] = [...gesture.points.values()];
		const apart = Math.hypot(one.x - two.x, one.y - two.y);
		const ratio = apart / gesture.apart;

		if (!gesture.engaged && Math.abs(ratio - 1) < PINCH_THRESHOLD) return;

		gesture.engaged = true;

		/* Held back until now: preventing earlier would stop a tap that had every
		   right to be one. */
		event.preventDefault();

		const wanted = Math.round(
			Math.min(FIT_CEILING, Math.max(FIT_FLOOR, gesture.from * ratio)));

		if (wanted !== cell) choose(String(wanted));
	}, [cell, choose]);

	const up = useCallback((event) => {
		const gesture = held.current;

		gesture.points.delete(event.pointerId);

		if (gesture.points.size < 2) {
			gesture.apart = 0;
			gesture.engaged = false;
		}
	}, []);

	return { onPointerDown: down, onPointerMove: move,
	         onPointerUp: up, onPointerCancel: up };
}

/* The size chooser.
 *
 * Every button here is a fixed comfortable size and none of them scales with
 * the setting: the first thing a person needs after picking cells too small to
 * hit is this control, so it must not have shrunk along with them. */
function Sizes ({ cell, choice, onChoose }) {
	const [open, setOpen] = useState(false);

	return html`
		<div class="sizes">
			<button
				class=${open ? "open" : ""}
				onPointerDown=${(event) => { event.preventDefault(); setOpen(!open); }}
			>size · ${cell}px</button>

			${open && html`
				<div class="choices">
					${SIZES.map((size) => html`
						<button
							key=${size.key}
							class=${size.key === choice ? "chosen" : ""}
							onPointerDown=${(event) => {
								event.preventDefault();
								onChoose(size.key);
								setOpen(false);
							}}
						>
							<i style=${{
								width: `${size.px || cell}px`,
								height: `${Math.min(size.px || cell, 24)}px`,
							}}></i>
							<span>${size.label}</span>
							<span class="measure">${size.px ? `${size.px}px` : `${cell}px`}</span>
						</button>`)}
				</div>`}
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
	const [notice, setNotice] = useState(null);
	const [service, setService] = useState(null);
	const [pages, setPages] = useState([]);
	const [chosen, setChosen] = useState(rememberedPage);
	const [locked, setLocked] = useState(rememberedLock);
	const [dragging, setDragging] = useState(false);
	const [adding, setAdding] = useState(null);
	const [clearing, setClearing] = useState(null);
	const [moved, setMoved] = useState({});
	const [touched, setTouched] = useState(null);

	const link = useRef(null);
	const expiries = useRef(new Map());
	const wanted = useRef(new Map());

	/* Which app the page being shown belongs to. In a ref because `request` is
	   built once and would otherwise close over whichever app had dialled in at
	   the moment it was made. */
	const owner = useRef(null);

	/* What kind each declared control is, kept in a ref rather than read from
	   render state. The frame handler is built once, so anything it closed over
	   at mount would be the empty declarations it had then — the same trap the
	   'changed' case below was already written around. */
	const kinds = useRef(new Map());

	/* Which block a hand is on, so the lines it is joined to can say so.
	 *
	 * Let go of at the document rather than on the block. A slider captures the
	 * pointer while it is being dragged, so the release lands on the slider and
	 * not necessarily anywhere this could see; the document is the one place
	 * every pointer ends up. Cleared to the same value it already holds is not
	 * a change, so an ordinary tap on a grid costs no render. */
	useEffect(() => {
		const let_go = () => setTouched((was) => (was === null ? was : null));

		document.addEventListener("pointerup", let_go);
		document.addEventListener("pointercancel", let_go);

		return () => {
			document.removeEventListener("pointerup", let_go);
			document.removeEventListener("pointercancel", let_go);
		};
	}, []);

	const drop = useCallback((path) => {
		setPending((was) => {
			if (!was.has(path)) return was;
			const now = new Map(was);
			now.delete(path);
			return now;
		});

		const timer = expiries.current.get(path);
		if (timer) { clearTimeout(timer); expiries.current.delete(path); }

		wanted.current.delete(path);
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

					for (const [app, offered] of Object.entries(listed)) {
						for (const [control, declared] of Object.entries(offered)) {
							kinds.current.set(`${app}/${control}`, declared);
						}
					}

					setApps((was) => ({ ...was, ...listed }));
					setPages(frame.pages || []);
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

					/* Anything still outstanding is asked for again, after the
					 * snapshot rather than before it, so the re-send lands on
					 * top of the state it was meant to change. Sets are
					 * absolute, so asking twice reaches the same place as
					 * asking once — which is what makes this safe. */
					for (const [path, request] of wanted.current) {
						if (request.app !== frame.app || !link.current) continue;

						const seq = link.current.set(request.app, path, request.value);
						if (seq !== null) setPending((was) => new Map(was).set(path, seq));
					}

					break;

				case "changed": {
					/* The face follows the app, whoever moved it.
					 *
					 * How to apply it depends on the kind of control. The shape
					 * of the path answers that on its own for three of these
					 * branches, and deliberately so — but not for all of them,
					 * and the two that need the declaration ask for it. A
					 * stack's parameter has exactly the shape of a grid cell,
					 * so shape alone sends it to the wrong branch.
					 *
					 * The kind comes from a ref rather than from `controls`:
					 * this handler is built once at mount, and anything it
					 * closed over then would be the empty declarations it had
					 * before any app dialled in. */
					const [control, ...rest] = frame.path.split("/");
					const declared = kinds.current.get(`${frame.app}/${control}`);

					setState((was) => {
						const app = { ...(was[frame.app] || {}) };

						if (rest.length === 3) {
							/* A note's own length or velocity: control, row,
							   step, field. Only ever sent for a note that is
							   there, so an absent one is left absent. */
							const grid = { ...(app[control] || {}) };
							const row = { ...(grid[rest[0]] || {}) };

							if (row[rest[1]]) {
								row[rest[1]] = { ...row[rest[1]], [rest[2]]: frame.v };
								grid[rest[0]] = row;
								app[control] = grid;
							}
						} else if (rest.length === 1) {
							app[control] = { ...(app[control] || {}), [rest[0]]: frame.v };
						} else if (rest.length === 2 && declared && declared.type === "recipe") {
							/* One parameter of one layer of a stack.
							
							   Reading the shape alone is not enough here, and
							   this is where that stops being true: a stack's
							   parameter has exactly the shape of a grid cell —
							   control, then two parts — so without the kind it
							   lands in the branch below, which reads the second
							   part as a step number and writes a list under the
							   layer's id. The knob then moves the music and
							   nothing on the glass. */
							const held = { ...(app[control] || {}) };

							held.layers = (held.layers || []).map((layer) =>
								layer.id === rest[0]
									? { ...layer, params: { ...(layer.params || {}), [rest[1]]: frame.v } }
									: layer);

							app[control] = held;
						} else if (rest.length === 2 && declared && declared.type === "note_grid") {
							/* Placing or taking away a note, which carries its
							   own shape rather than being present or absent. */
							const grid = { ...(app[control] || {}) };
							const row = { ...(grid[rest[0]] || {}) };

							if (frame.v) {
								row[rest[1]] = row[rest[1]] || {
									length: declared.default_length || 1,
									velocity: declared.default_velocity || 100 };
							} else {
								delete row[rest[1]];
							}

							grid[rest[0]] = row;
							app[control] = grid;
						} else if (rest.length === 2) {
							const grid = { ...(app[control] || {}) };
							const list = new Set(grid[rest[0]] || []);
							frame.v ? list.add(Number(rest[1])) : list.delete(Number(rest[1]));
							grid[rest[0]] = [...list].sort((a, b) => a - b);
							app[control] = grid;
						}

						return { ...was, [frame.app]: app };
					});

					/* Answered in substance: the app now holds what was asked
					 * for, whether it credits this panel or not. A transport's
					 * confirmation arrives as the app's own doing, so waiting
					 * for our name on it would leave the request pending until
					 * it timed out and flashed as a failure. */
					if (frame.client === clientId || wanted.current.get(frame.path)?.value === frame.v) {
						drop(frame.path);
					}

					break;
				}

				case "service":
					setService({ version: frame.version, build: frame.build });
					break;

				case "ack":
					break;

				case "nack":
					/* The request was refused: the ring goes and the cell says so
					 * briefly. The face never moved, so there is nothing to undo. */
					drop(frame.path);
					flashFailure(frame.path);
					setNotice(frame.reason || "refused");
					setTimeout(() => setNotice(null), 4000);
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

		const rejoin = () => { if (!document.hidden && link.current) link.current.resync(); };

		document.addEventListener("visibilitychange", rejoin);
		window.addEventListener("pageshow", rejoin);

		return () => {
			document.removeEventListener("visibilitychange", rejoin);
			window.removeEventListener("pageshow", rejoin);
		};
	}, [drop, flashFailure]);

	const choosePage = useCallback((id) => {
		setChosen(id);

		try {
			localStorage.setItem(PAGE_KEY, id);
		} catch (error) {
			/* A panel that cannot remember still works; it opens on the first
			   page every time. */
		}
	}, []);

	const request = useCallback((path, value) => {
		const app = owner.current;
		if (!app || !link.current) return;

		const seq = link.current.set(app, path, value);
		if (seq === null) return;

		wanted.current.set(path, { app, value });
		setPending((was) => new Map(was).set(path, seq));

		/* A ring that is never confirmed must not sit there for ever: after
		 * five seconds the request is abandoned and the face — which was
		 * always the truth — is all that is left. */
		expiries.current.set(path, setTimeout(() => { drop(path); flashFailure(path); }, PENDING_EXPIRES));
	}, [drop, flashFailure]);

	/* Whichever app declared the page being shown, rather than whichever
	   dialled in first. Only one does today, so this changes nothing now — but
	   a page already carries the name of its own app (#2075), and sending a tap
	   to the wrong one would have it correctly refused by an app that has never
	   heard of the path. */
	const onPage = pages.find((one) => one.id === chosen) || pages[0] || null;
	const appName = (onPage && onPage.app) || Object.keys(apps)[0];
	const controls = appName ? apps[appName] || {} : {};
	const up = appName ? present[appName] !== false : false;

	/* Every grid the app declared, not the first one it declared. Two patterns
	   driving one instrument belong on one page as stacked blocks, which is
	   what Simon settled in #1944 — and a page that showed only the first of
	   them would be quietly wrong rather than obviously incomplete. */
	const declaredGrids = Object.keys(controls).filter(
		(name) => DRAWN.includes(controls[name].type) || controls[name].unsupported);

	/* Which page is showing. A remembered choice for a page that is no longer
	   offered falls back to the first without being forgotten: a composition
	   restarted with one pattern missing should not cost a performer the page
	   they had set, once it comes back. */
	const page = onPage;

	owner.current = appName;

	/* A page names the parts it carries, so a part on two pages appears on
	   both and needs nothing to keep them together — each draws the app's own
	   state (#2046). An app that declared no pages shows everything, which is
	   what every panel did before pages existed. */
	const gridNames = page
		? declaredGrids.filter((name) => (page.parts || []).includes(name))
		: declaredGrids;

	const kindOf = (name) => controls[name].type;

	/* A stack says which pattern it contributes to, and that one fact places its
	   buttons: the pattern grows an "add a generator", not the stack. */
	const stackFor = (name) => Object.keys(controls).find(
		(one) => kindOf(one) === "recipe" && controls[one].builds === name);

	const tidied = (word) => String(word).replace(/_/g, " ");

	/* What a control is called on the glass: the app's own word for it, or its
	   address tidied up when the app offered none (#2071). */
	const named = (name) => (controls[name] && controls[name].title) || tidied(name);

	/* Every window on this page, which is no longer the same thing as every
	   control on it.
	 *
	 * A stack of generators is not one tall block any more: each contribution in
	 * it is a window of its own, placed and moved like any other (#2109). So a
	 * window carries the control it draws, the layer it draws from when it is a
	 * contribution, and its key — which is what the lattice, the stacking order
	 * and the saved arrangement all know it by.
	 *
	 * A contribution appears wherever its stack is named, which is how a person
	 * chooses to see one: a page carrying the pattern alone is the uncluttered
	 * grid Simon described wanting, and a page carrying both is the one given
	 * over to building it (#2085). Inheriting the pattern's pages instead would
	 * put generators on the page that was made without them.
	 *
	 * Contributions come after the patterns rather than beside them, and that is
	 * deliberate. A starting position is worked out by flowing the list left to
	 * right, so where a block lands depends on everything before it; adding a
	 * generator appends, and appending moves nothing that is already down. */
	const windows = [];
	const contributions = [];

	for (const name of gridNames) {
		if (controls[name].unsupported) {
			windows.push({ key: name, control: name, title: named(name),
			               rows: 3, steps: PARAM_CELLS });
			continue;
		}

		if (kindOf(name) === "recipe") {
			const held = ((state[appName] || {})[name] || {}).layers || [];
			const offered = controls[name].generators || [];
			const builds = controls[name].builds;
			const feeds = builds && gridNames.includes(builds) ? builds : null;

			for (const layer of held) {
				const generator = offered.find((one) => one.name === layer.generator);

				contributions.push({
					key: `${name}/${layer.id}`,
					control: name, layer, layers: held, offered: generator, feeds,

					/* "Euclidean 1", where the number belongs to that layer for
					   the whole of its life — a neighbour being removed never
					   moves it. The pattern is named beside it so that a line
					   crossing another line is not the only thing on the glass
					   saying what feeds what. */
					title: `${tidied(layer.generator || "?")}`
						+ (layer.index ? ` ${layer.index}` : "")
						+ (builds ? ` · ${named(builds)}` : ""),

					rows: 1 + (generator ? generator.parameters.length : 1),
					steps: PARAM_CELLS,
				});
			}

			/* A stack keeps a window of its own when the pattern it feeds is not
			   on this page, and only then: otherwise the way to add a generator
			   would be on a page the person is not looking at. */
			if (!feeds) {
				windows.push({ key: name, control: name, title: named(name),
				               add: name, rows: 2, steps: PARAM_CELLS });
			}

			continue;
		}

		if (kindOf(name) === "params") {
			windows.push({ key: name, control: name, title: named(name),
			               rows: Math.max(1, (controls[name].fields || []).length),
			               steps: PARAM_CELLS });
			continue;
		}

		/* A pitched pattern is as tall as its rows plus the velocity lane
		   beneath them, which is what the fit has to solve for rather than the
		   rows alone. Every pattern carries a footer, because every pattern can
		   be cleared. */
		windows.push({
			key: name, control: name, title: named(name),
			add: stackFor(name) || null, clear: true,
			rows: Math.min(controls[name].rows.length, controls[name].visible_rows || Infinity)
				+ (kindOf(name) === "note_grid" ? LANE_CELLS : 0) + 1,
			steps: controls[name].steps,
		});
	}

	const drawn = [...windows, ...contributions];
	const blocks = drawn.map(
		(one) => ({ name: one.key, rows: Math.max(1, one.rows), steps: one.steps }));

	/* Which windows are joined, and which way round. A contribution feeds a
	   pattern, so the head of the line is at the pattern; the ordering is the
	   direction, which is the field #2109 asked to exist before anything needs
	   the other one. */
	const joins = contributions
		.filter((one) => one.feeds)
		.map((one) => ({ from: one.key, to: one.feeds }));

	const pageId = page ? page.id : "";
	const arranged = moved[pageId] || {};

	/* Move and raise are the same write with one difference, so they are one
	   function: a drag says where, a tap from the inventory says only that this
	   block should be on top. Either way the block goes to the end of the
	   order, which is what "the last one moved is on top" means. */
	const rearrange = useCallback((name, at) => {
		setMoved((was) => {
			const forPage = was[pageId] || {};
			const order = [...(forPage.order || []).filter((one) => one !== name), name];
			const placed = at
				? { ...(forPage.placed || {}), [name]: at }
				: forPage.placed || {};

			return { ...was, [pageId]: { placed, order } };
		});
	}, [pageId]);

	/* Where the parts sit, until somebody moves them.
	 *
	 * Worked out once per page rather than on every resize: a starting
	 * arrangement that shuffled itself as the glass changed would be a layout
	 * nobody chose and nobody could rely on. It wraps at whatever a panel this
	 * wide would hold at the tested cell size, which is a fixed number for a
	 * given panel and so cannot chase its own answer. */
	const defaults = useMemo(
		() => autoPlace(blocks, acrossAtTestedSize()),
		[pageId, blocks.map((block) => block.name).join(",")]);

	/* Three layers, in order of authority. Where the panel would put a part
	   that nobody has placed; then the arrangement the composition is keeping,
	   which is the shared one every panel sees; then anything moved here since,
	   which is what the finger is doing right now. */
	const kept = (page && page.layout) || [];
	const keptPlaces = Object.fromEntries(kept.map((one) => [one.name, { x: one.x, y: one.y }]));

	const layout = { ...defaults, ...keptPlaces, ...(arranged.placed || {}) };

	/* Drawn back to front. A name that has been moved sits after every name
	   that has not, and later moves sit after earlier ones.
	
	   This is a stacking order and not a drawing order, which is the whole
	   point: the blocks are rendered in the order the app declared them and
	   never rearranged in the document, because moving a node releases the
	   pointer capture a drag depends on. Raising a block therefore changes one
	   number on it rather than its place among its siblings. Touch survived the
	   old way — a touch pointer is captured implicitly — and a mouse did not,
	   so a drag with a mouse died after its first pixel whenever the block was
	   not already on top. */
	const order = (arranged.order && arranged.order.length)
		? arranged.order
		: kept.map((one) => one.name);

	const keys = drawn.map((one) => one.key);

	const stacked = [
		...keys.filter((key) => !order.includes(key)),
		...order.filter((key) => keys.includes(key)),
	];

	/* Asked for before the page can return early, because a hook must be. It is
	   given every block's shape and where each one sits, because an arrangement
	   is only as large as its furthest corner. */
	const size = useCellSize(blocks, layout, dragging);

	const pinch = usePinch(size.cell, size.choose);

	/* Where every block on this page has ended up, sent to the app that owns
	   the page. Called when a finger lifts from a block that actually moved. */
	const keep = () => {
		if (!appName || !link.current) return;

		link.current.layout(appName, pageId, stacked
			.filter((name) => layout[name])
			.map((name) => ({ name, x: layout[name].x, y: layout[name].y })));
	};

	/* Both halves have to be known before they can disagree: a page served
	   without a stamp, or a service too old to send one, is not evidence of
	   anything and must not raise a warning it cannot justify. */
	const stale = Boolean(service && service.build && pageBuild && service.build !== pageBuild);

	const transportName = Object.keys(controls).find((name) => controls[name].type === "transport");
	const transportFields = transportName ? (state[appName] || {})[transportName] || {} : {};

	if (!declaredGrids.length) {
		return html`
			<div class="bar">
				<span class="spacer"></span>
				<span class=${`lamp ${status === "up" ? "up" : ""}`}>${status === "up" ? "connected" : "offline"}</span>
				<${Build} service=${service} stale=${stale} />
			</div>
			<div class="notice">
				${status === "up"
					? "Waiting for a music app to dial in and say what it offers."
					: "Waiting for the Superintendent service."}
			</div>`;
	}

	return html`
		<div class="bar">
			${transportName && html`
				<${Transport} control=${controls[transportName]} name=${transportName}
					fields=${transportFields} up=${up} onSet=${request} />`}
			<${Pages} pages=${pages} current=${page && page.id} onChoose=${choosePage} />
			<button
				class=${`latch ${locked ? "" : "open"}`}
				title=${locked ? "the layout is held still" : "blocks can be moved"}
				onPointerDown=${(event) => {
					event.preventDefault();
					setLocked(!locked);
					rememberLock(!locked);
				}}
			>${locked ? "🔒" : "🔓"} LAYOUT</button>
			${!locked && html`
				<${Inventory} names=${stacked} titles=${Object.fromEntries(
					drawn.map((one) => [one.key, one.title]))}
					onRaise=${(who) => rearrange(who, null)} />`}
			<span class="spacer"></span>
			${notice && html`<span class="warn">${notice}</span>`}
			${!up && !notice && html`<span class="warn">not running — taps will be refused</span>`}
			<${Sizes} cell=${size.cell} choice=${size.choice} onChoose=${size.choose} />
			<span class=${`lamp ${status === "up" && up ? "up" : ""}`}>
				${status !== "up" ? "no service" : up ? "connected" : "app gone"}
			</span>
			<${Build} service=${service} stale=${stale} />
		</div>
		<div
			class=${`grid-wrap ${up ? "" : "absent"} ${locked ? "" : "unlocked"}`}
			ref=${size.wrap}
			...${pinch}
		>
			${drawn.map((one) => html`
				<${Part} key=${one.key} name=${one.key} title=${one.title}
					at=${layout[one.key]} cell=${size.cell} depth=${stacked.indexOf(one.key)}
					locked=${locked}
					onMove=${(who, x, y) => rearrange(who, { x, y })}
					onRaise=${(who) => rearrange(who, null)}
					onHold=${setDragging}
					onSettled=${keep}
					onTouch=${setTouched}
					footer=${html`
						<${Footer}
							onAdd=${one.add ? () => setAdding(one.add) : null}
							onClear=${one.clear ? () => setClearing(one.control) : null} />`}>
					${one.layer
						? html`
							<${Contribution} name=${one.control} layer=${one.layer}
								layers=${one.layers} offered=${one.offered} onSet=${request} />`
						: controls[one.control].unsupported
						? html`
							<div class="unsupported">
								This service does not know how to draw a
								<b>${controls[one.control].unsupported}</b>. It is older than the
								application that declared it, and is not keeping this
								control's state — so nothing here would follow the music.
							</div>`
						: kindOf(one.control) === "recipe"
						? html`<${Orphan} builds=${controls[one.control].builds} />`
						: kindOf(one.control) === "params"
						? html`
							<${Params} name=${one.control} fields=${controls[one.control].fields || []}
								values=${(state[appName] || {})[one.control] || {}}
								cell=${size.cell} onSet=${request} />`
						: kindOf(one.control) === "note_grid"
						? html`
							<${NoteGrid} name=${one.control} control=${controls[one.control]}
								rows=${controls[one.control].rows} steps=${controls[one.control].steps}
								notes=${(state[appName] || {})[one.control] || {}} cell=${size.cell}
								window=${controls[one.control].visible_rows}
								pending=${pending} failed=${failed} onSet=${request} />
							<${VelocityLane} name=${one.control} rows=${controls[one.control].rows}
								steps=${controls[one.control].steps} cell=${size.cell}
								notes=${(state[appName] || {})[one.control] || {}}
								range=${controls[one.control].velocity_range} onSet=${request} />`
						: html`
							<${Grid} control=${one.control} rows=${controls[one.control].rows}
								steps=${controls[one.control].steps}
								cells=${(state[appName] || {})[one.control] || {}}
								visible=${controls[one.control].visible_rows} cell=${size.cell}
								pending=${pending} failed=${failed} onTap=${request} />`}
					${up && one.clear && html`
						<${Playhead} anchor=${anchor} steps=${controls[one.control].steps}
							beats=${controls[one.control].beats || 4}
							paused=${transportFields.paused === true} />`}
				<//>`)}

			${/* Told what could have moved a line, because measuring is what this
			     does and nothing else in the page will tell it. */ ""}
			<${Connections} box=${size.wrap} joins=${joins} touched=${touched}
				when=${`${size.cell}|${JSON.stringify(layout)}`
					+ `|${joins.map((join) => `${join.from}>${join.to}`).join(",")}`} />
		</div>

		${adding && controls[adding] && html`
			<${Sheet} title="add a generator" onClose=${() => setAdding(null)}>
				${(controls[adding].generators || []).map((generator) => html`
					<button
						key=${generator.name}
						class=${`offer ${generator.partial ? "partial" : ""}`}
						disabled=${generator.partial}
						onPointerDown=${(event) => {
							event.preventDefault();

							const held = ((state[appName] || {})[adding] || {}).layers || [];

							/* An id has to survive a round trip and be unique among
							   its neighbours. The clock alone is not enough: two
							   taps inside a millisecond are a stutter rather than an
							   impossibility on a surface meant to be played. */
							request(`${adding}/layers`, [...held, {
								id: `l${Date.now().toString(36)}`
									+ `${Math.floor(Math.random() * 46656).toString(36)}`,
								kind: "generator",
								generator: generator.name,
								params: {},
							}]);

							setAdding(null);
						}}
					>
						<b>${generator.name}</b>
						<i>${generator.partial
							? "takes something this panel cannot draw yet"
							: generator.summary}</i>
					</button>`)}
			<//>`}

		${clearing && html`
			<${Sheet} title="clear this pattern" onClose=${() => setClearing(null)}>
				<p class="ask">
					${/* Spaces kept inside the spans: the template collapses the
					     whitespace around an element, and "taken offDRM1" is what
					     that looks like on the glass. */ ""}
					<span>${countOf((state[appName] || {})[clearing])} steps will be taken off </span>
					<b>${controls[clearing].title || clearing}</b>
					<span>. There is no undo.</span>
				</p>
				<div class="answers">
					<button
						onPointerDown=${(event) => { event.preventDefault(); setClearing(null); }}
					>keep them</button>
					<button
						class="danger"
						onPointerDown=${(event) => {
							event.preventDefault();
							request(`${clearing}/rows`, {});
							setClearing(null);
						}}
					>clear</button>
				</div>
			<//>`}`;
}

/* How much a person is about to lose, counted so the dialog can say it.
 *
 * The count is the whole reason a dialog beats an armed button here: only a
 * dialog can say *what* is about to go, and a pattern may be the only copy
 * there is until #2067 is settled. */
function countOf (grid) {
	return Object.values(grid || {}).reduce(
		(total, row) => total + (Array.isArray(row) ? row.length : Object.keys(row || {}).length), 0);
}

render(html`<${Panel} />`, document.getElementById("panel"));

/* A long press must not offer a context menu, and a double tap must not zoom:
 * both are the browser deciding a musician's gesture means something else. */
document.addEventListener("contextmenu", (event) => event.preventDefault());
document.addEventListener("gesturestart", (event) => event.preventDefault());
