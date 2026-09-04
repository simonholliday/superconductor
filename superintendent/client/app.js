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

import { html, render, useState, useEffect, useRef, useCallback, useMemo }
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
			this.send({ t: "hello", contract: "1.3.0", client: clientId, page: rememberedPage(), ver: {}, token: null });
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
			this.send({ t: "hello", contract: "1.3.0", client: clientId, page: rememberedPage(), ver: {}, token: null });
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

	/* A page's whole arrangement, handed back to the app that owns the page.
	 * Positions in lattice cells and no sizes, in the order the parts are
	 * stacked — so the last entry is the one on top (#2078). */
	arrange (app, page, parts) {
		const seq = ++this.seq;
		return this.send({ t: "arrange", app, page, parts, client: clientId, seq }) ? seq : null;
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
function Part ({ title, name, at, cell, depth, arranging, onMove, onRaise, children }) {
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
		if (!arranging) return;

		event.preventDefault();
		event.currentTarget.setPointerCapture(event.pointerId);

		held.current = {
			pointer: event.pointerId,
			fromX: event.clientX, fromY: event.clientY,
			x: at ? at.x : 0, y: at ? at.y : 0,
		};

		onRaise(name);
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

		if (!at || x !== at.x || y !== at.y) onMove(name, x, y);
	};

	const release = (event) => {
		if (held.current && held.current.pointer === event.pointerId) held.current = null;
	};

	return html`
		<section class="part" data-part=${name} style=${place}>
			<header
				class="part-title"
				onPointerDown=${grab}
				onPointerMove=${move}
				onPointerUp=${release}
				onPointerCancel=${release}
			>${title || name.replace(/_/g, " ")}</header>
			<div class="part-body">${children}</div>
		</section>`;
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
		if (!anchor || !bar.current) return;

		let frame;
		const grid = bar.current.parentElement.querySelector(".grid");

		const move = () => {
			const first = grid && grid.children[1];
			const second = grid && grid.children[2];

			if (first && anchor.interval) {
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
	}, [anchor, steps, beats]);

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

	const height = Math.max(TITLE_FLOOR, cell)
		+ block.rows * cell + (block.rows - 1) * GAP + chrome.y;

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
		   down. Nothing measured, because nothing here needs pixels. */
		const wide = LABEL_CELLS + block.steps;
		const high = 1 + block.rows;

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

function useCellSize (blocks, layout) {
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

	const choose = useCallback((key) => {
		setChoice(key);

		try {
			localStorage.setItem(SIZE_KEY, key);
		} catch (error) {
			/* As above: forgetting is the only consequence. */
		}
	}, []);

	useEffect(() => {
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
					const at = layout[block.name] || { x: 0, y: 0 };
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
	}, [choice, JSON.stringify(blocks), JSON.stringify(layout)]);

	useEffect(() => {
		document.documentElement.style.setProperty("--cell", `${cell}px`);
	}, [cell]);

	return { wrap, cell, choice, choose };
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
	const [arranging, setArranging] = useState(false);
	const [moved, setMoved] = useState({});

	const link = useRef(null);
	const expiries = useRef(new Map());
	const wanted = useRef(new Map());

	/* What kind each declared control is, kept in a ref rather than read from
	   render state. The frame handler is built once, so anything it closed over
	   at mount would be the empty declarations it had then — the same trap the
	   'changed' case below was already written around. */
	const kinds = useRef(new Map());

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
					 * How to apply it depends on the kind of control, and the
					 * path says which: three parts address a cell of a grid,
					 * two a named field. Reading the shape rather than looking
					 * the kind up keeps this free of the declarations, which a
					 * handler built once at mount would only ever see empty. */
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
		const app = Object.keys(apps)[0];
		if (!app || !link.current) return;

		const seq = link.current.set(app, path, value);
		if (seq === null) return;

		wanted.current.set(path, { app, value });
		setPending((was) => new Map(was).set(path, seq));

		/* A ring that is never confirmed must not sit there for ever: after
		 * five seconds the request is abandoned and the face — which was
		 * always the truth — is all that is left. */
		expiries.current.set(path, setTimeout(() => { drop(path); flashFailure(path); }, PENDING_EXPIRES));
	}, [apps, drop, flashFailure]);

	const appName = Object.keys(apps)[0];
	const controls = appName ? apps[appName] : {};
	const up = appName ? present[appName] !== false : false;

	/* Every grid the app declared, not the first one it declared. Two patterns
	   driving one instrument belong on one page as stacked blocks, which is
	   what Simon settled in #1944 — and a page that showed only the first of
	   them would be quietly wrong rather than obviously incomplete. */
	const declaredGrids = Object.keys(controls).filter(
		(name) => controls[name].type === "step_grid" || controls[name].type === "note_grid");

	/* Which page is showing. A remembered choice for a page that is no longer
	   offered falls back to the first without being forgotten: a composition
	   restarted with one pattern missing should not cost a performer the page
	   they had set, once it comes back. */
	const page = pages.find((one) => one.id === chosen) || pages[0] || null;

	/* A page names the parts it carries, so a part on two pages appears on
	   both and needs nothing to keep them together — each draws the app's own
	   state (#2046). An app that declared no pages shows everything, which is
	   what every panel did before pages existed. */
	const gridNames = page
		? declaredGrids.filter((name) => (page.parts || []).includes(name))
		: declaredGrids;

	const kindOf = (name) => controls[name].type;

	/* A pitched pattern is as tall as its rows plus the velocity lane beneath
	   them, which is what the fit has to solve for rather than the rows alone. */
	const blocks = gridNames.map((name) => ({
		name,
		rows: Math.min(controls[name].rows.length, controls[name].visible_rows || Infinity)
			+ (kindOf(name) === "note_grid" ? LANE_CELLS : 0),
		steps: controls[name].steps }));

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
	   that has not, and later moves sit after earlier ones. */
	const order = (arranged.order && arranged.order.length)
		? arranged.order
		: kept.map((one) => one.name);

	const stacked = [
		...gridNames.filter((name) => !order.includes(name)),
		...order.filter((name) => gridNames.includes(name)),
	];

	/* Asked for before the page can return early, because a hook must be. It is
	   given every block's shape and where each one sits, because an arrangement
	   is only as large as its furthest corner. */
	const size = useCellSize(blocks, layout);

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
				class=${`arrange ${arranging ? "latched" : ""}`}
				onPointerDown=${(event) => {
					event.preventDefault();

					/* Sent on the way out rather than while dragging, so a drag
					 * in progress is never half-saved, and so an accidental
					 * nudge is one write rather than twenty (#2075). */
					if (arranging && appName && link.current) {
						link.current.arrange(appName, pageId, stacked.map((name) => ({
							name, x: layout[name].x, y: layout[name].y })));
					}

					setArranging(!arranging);
				}}
			>${arranging ? "DONE" : "ARRANGE"}</button>
			${arranging && html`
				<${Inventory} names=${stacked} titles=${Object.fromEntries(
					gridNames.map((name) => [name, controls[name].title]))}
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
		<div class=${`grid-wrap ${up ? "" : "absent"} ${arranging ? "arranging" : ""}`} ref=${size.wrap}>
			${stacked.map((name, index) => html`
				<${Part} key=${name} name=${name} title=${controls[name].title}
					at=${layout[name]} cell=${size.cell} depth=${index}
					arranging=${arranging}
					onMove=${(who, x, y) => rearrange(who, { x, y })}
					onRaise=${(who) => rearrange(who, null)}>
					${kindOf(name) === "note_grid"
						? html`
							<${NoteGrid} name=${name} control=${controls[name]}
								rows=${controls[name].rows} steps=${controls[name].steps}
								notes=${(state[appName] || {})[name] || {}} cell=${size.cell}
								window=${controls[name].visible_rows}
								pending=${pending} failed=${failed} onSet=${request} />
							<${VelocityLane} name=${name} rows=${controls[name].rows}
								steps=${controls[name].steps} cell=${size.cell}
								notes=${(state[appName] || {})[name] || {}}
								range=${controls[name].velocity_range} onSet=${request} />`
						: html`
							<${Grid} control=${name} rows=${controls[name].rows} steps=${controls[name].steps}
								cells=${(state[appName] || {})[name] || {}}
								visible=${controls[name].visible_rows} cell=${size.cell}
								pending=${pending} failed=${failed} onTap=${request} />`}
					${up && html`<${Playhead} anchor=${anchor} steps=${controls[name].steps}
						beats=${controls[name].beats || 4} paused=${transportFields.paused === true} />`}
				<//>`)}
		</div>`;
}

render(html`<${Panel} />`, document.getElementById("panel"));

/* A long press must not offer a context menu, and a double tap must not zoom:
 * both are the browser deciding a musician's gesture means something else. */
document.addEventListener("contextmenu", (event) => event.preventDefault());
document.addEventListener("gesturestart", (event) => event.preventDefault());
