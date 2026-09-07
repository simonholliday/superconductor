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

const TRIPS_KEPT = 60;
/* How many round trips to remember: two minutes at one ping every two seconds,
   which is long enough for a bad moment to still be on the readout when you
   look up from playing. */
const STALE_AFTER = 6000;
const CONTRACT = "1.17.0";
/* The protocol version this client speaks, in one place.
 *
 * It cannot be shared with Python, so a test asserts the two agree — but it can
 * at least be written once here rather than spelled by hand at each greeting. */

/* How a version the service speaks differs from this page's, if it does (#2164).
 *
 * **A second implementation of `protocol.contract_gap`, and it has to be**, for
 * a reason worth reading before deciding to tidy it away. The obvious design is
 * for the service to compare the two — it knows both — and put the verdict in a
 * frame. That fails in exactly the case that matters. A panel *newer* than the
 * service is what costs a session here, and the service is then by definition
 * too old to have been taught to send the verdict, so nothing would arrive and
 * nothing would be said. The only half that can catch it is the half that is
 * new, which is this one.
 *
 * The rule is kept trivial for the same reason: compare the first number, and
 * otherwise compare the rest. Both implementations are held to one table of
 * pairs by a test rather than by care. */
const contractGap = (spoken) => {
	if (spoken === CONTRACT) return null;

	const parts = String(spoken ?? "").split(".");

	if (parts.length !== 3 || !parts.every((one) => /^\d+$/.test(one))) return "unreadable";

	const theirs = parts.map(Number);
	const ours = CONTRACT.split(".").map(Number);

	if (theirs[0] !== ours[0]) return "major";

	for (let at = 1; at < 3; at += 1) {
		if (theirs[at] !== ours[at]) return theirs[at] < ours[at] ? "older" : "newer";
	}

	return null;
};

/* The greeting, written once.
 *
 * It was written out twice — on opening a socket and again on waking — with the
 * contract version spelled by hand in both. A test does catch a divergence from
 * Python, so this was a maintenance nuisance rather than a hazard; but the same
 * literal repeated is exactly what the tools got wrong three separate ways. */
const greeting = () => ({
	t: "hello", contract: CONTRACT, client: clientId,
	page: rememberedPage(), ver: {}, token: null,
});

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

/* A mark on the lattice: it grows with the cell, between a floor where it stops
 * being legible and a ceiling where it starts to dominate what it marks.
 *
 * The same rule as the type scale, and the stylesheet says the whole of it. This
 * is the half of it that cannot live in CSS, because an SVG path is arithmetic
 * rather than layout — which is exactly how the arrowhead came to be a constant
 * while everything around it scaled. Simon found that by zooming. */
const marked = (cell, floor, share, ceiling) =>
	Math.min(ceiling, Math.max(floor, cell * share));

const JACK = { floor: 6, share: 0.17, ceiling: 12 };
/* How large the fitting is where a cable meets a block.
 *
 * "Right now it might be possible to misinterpret a line as going *behind* an
 * item, since we cannot see the join" — Simon, and he was right. It began as a
 * dot saying only "the line stops here". It is a fitting now, and it says one
 * thing more: **the source end is a plug and the destination end is a socket**,
 * so a cable declares which way it runs by being plugged into something.
 *
 * That is what replaced the arrowhead. A head drawn at a line's middle was a
 * triangle floating in space with nothing physical about it, and at the end it
 * pointed to it merged with every other head arriving at the same block —
 * Simon found that with three of them. A plug and a socket cannot merge,
 * because they are at opposite ends of their own cable.
 */

const SAG_FLOOR = 10;
const SAG_SHARE = 0.14;
const SAG_CEILING = 54;
/* How far a cable hangs between its two ends.
 *
 * **Not decoration.** A sag is what makes two crossing cables read as two
 * cables rather than as an X, which is the whole reason a real patchbay is
 * legible at all — and this page will have several once a grid feeds three
 * patterns. Proportional to the span, so a short link barely dips and a long
 * one hangs, which is also what a real lead does.
 */

const ANCHOR = { floor: 3.5, share: 0.11, ceiling: 7 };
/* How far a cable's end is held off the block it meets.
 *
 * Once a dot marking where a line stopped; the fitting drawn there is a plug or
 * a socket now (see `JACK`) and this is only the inset. It still earns its own
 * number: a cable that ended exactly on an edge would have its fitting half
 * behind the block, which is the ambiguity Simon reported in the first place —
 * "it might be possible to misinterpret a line as going *behind* an item". */

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
const ACTION_FLASH = 1400;
/* Long enough to outlast the finger that caused it.  The stylesheet holds the
   fill for the first third and fades it over the rest, so this only has to be
   the whole of that — clearing the class sooner would cut the fade off. */


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

/* The sizes a cell can be.
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

const ZOOM_FLOOR = 6;
/* How small a pinch may make a cell, as against how small the automatic fit
   will choose. They are different questions. The fit is picking a size somebody
   has to work at, so it stops where a control stops being usable; a pinch is a
   person deciding what they want to look at, and asking to see the whole
   composition at once is a reasonable thing to want. */

const OVERVIEW_AT = 16;
/* Below this a cell is too small to be aimed at, so the page stops pretending
   otherwise: grids stop taking taps and draw as shapes, and the titles — which
   have a legibility floor of their own and never scaled — go on saying which
   block is which. That is the whole purpose of the view, since it exists to be
   read before choosing what to zoom back into. */
const FIT_SLACK = 2;

/* The gap between cells. Written in the stylesheet too, and the two must agree;
   there is a test that says so. */
const GAP = 4;

const PAD = GAP * 2;
/* The inset between a block's frame and what is in it, in pixels.
 *
 * The same number as the stylesheet's `--pad`, and it is known here for the same
 * reason `GAP` is: a block's frame makes it wider than the cells its grid
 * occupies, so a starting arrangement that counted only the grid would quietly
 * eat the lane it leaves between blocks.
 *
 * Declared here rather than beside `SEPARATION`, which is where it reads best
 * and where it cannot go: `GAP` is below that, and a `const` read before its own
 * declaration throws on evaluation. The module then never runs and the page is
 * blank — with the syntax check passing, because it is not a syntax error.
 * The page suite is what finds this, and did. */
const LABEL_CELLS = 3;
const TITLE_FLOOR = 24;
const LANE_CELLS = 3;
const NOTE_CONTROL_CELLS = 2;
/* The two rows a pitched pattern's settings take under its lane: what gestures
   snap to, and the selected note's length. Counted here because a block's
   height is decided before anything is drawn, and a strip the fit did not know
   about is a strip that overflows its own block. */
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

const GRID_KINDS = ["step_grid", "note_grid"];
/* The kinds whose state is rows, and which therefore address all of it at once
   as `control/rows`. Shape alone cannot tell that path from a params field or a
   transport field called `rows`, so the kind is asked for — the same reason the
   recipe branch beside it asks. */

const DRAWN = ["step_grid", "note_grid", "params", "recipe"];
/* The kinds a page draws as blocks of their own. A transport is not among them:
   it belongs in the header, with what is constant across pages (#2075). */

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
	constructor (onFrame, onStatus, onTrips) {
		this.onFrame = onFrame;
		this.onStatus = onStatus;
		this.onTrips = onTrips;
		this.socket = null;
		this.delay = RECONNECT_FLOOR;
		this.seq = 0;
		this.lastInbound = 0;

		/* How long the last few round trips took, newest last. */
		this.trips = [];
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
			this.send(greeting());
		};

		this.socket.onmessage = (message) => {
			this.lastInbound = performance.now();

			let frame;

			/* **Two different failures, two different sentences.** One catch
			   round both said "unreadable frame" for a frame that read
			   perfectly well and a handler that threw — which is a lie about
			   whose fault it is, and it cost a debugging cycle: a typo in this
			   very handler was reported as a protocol problem while every pong
			   was silently dropped. */
			try {
				frame = JSON.parse(message.data);

				/* **The round trip, which was being thrown away.** A pong
				   echoes the timestamp its ping carried, so the panel can
				   measure its own network without anything being built for it —
				   and the five-second abandon timer has been carried through
				   three reviews on the grounds that nobody has disproved it,
				   because nobody could see this number. The worst of a window
				   is what matters rather than the typical: the question the
				   timer answers is how long a good request can take. */
			} catch (error) {
				console.warn("frame could not be read", error);
				return;
			}

			try {
				if (frame.t === "pong" && typeof frame.ts === "number") {
					this.trips.push(performance.now() - frame.ts);

					if (this.trips.length > TRIPS_KEPT) this.trips.shift();

					this.onTrips(this.trips.slice());
				}

				this.onFrame(frame);
			} catch (error) {
				console.error("this panel failed to handle a", frame.t, "frame", error);
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
			this.send(greeting());
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
function Window ({ rows, visible, cell, tight, children }) {
	const seen = useRef(null);
	const windowed = Boolean(visible && visible < rows);

	/* Where the window sits on what it is looking at, as two fractions. */
	const [view, setView] = useState({ from: 0, span: 1 });

	/* The same fraction, kept where an effect can read it without depending on
	   it. A resize has to know where the window was *before* the resize, and
	   state read through the dependency list would either be stale by design or
	   make the effect run again for its own answer. */
	const at = useRef(0);
	const opened = useRef(false);

	const measure = useCallback(() => {
		const box = seen.current;

		if (!box || !box.scrollHeight) return;

		at.current = box.scrollTop / box.scrollHeight;

		setView({ from: at.current, span: box.clientHeight / box.scrollHeight });
	}, []);

	useEffect(() => {
		const box = seen.current;

		if (!windowed) { opened.current = false; measure(); return; }
		if (!box) return;

		if (!opened.current) {
			/* Opened at the bottom, which on a grid drawn high to low is the
			   lowest notes — where a bass line lives. **On opening, and only
			   then.** `cell` is in this effect's dependencies, so every step of
			   a pinch, every change of the size setting and every re-fit was
			   also throwing the window back to its lowest rows: a person
			   zooming in on the top of a pattern watched it run away from them
			   at each step. Opening at the bottom is a mount behaviour and the
			   dependency list had quietly made it a resize behaviour too. */
			box.scrollTop = box.scrollHeight;
			opened.current = true;

		} else {
			/* A resize keeps what was being looked at. The content has just
			   changed height, so the same fraction is the same music. */
			box.scrollTop = at.current * box.scrollHeight;
		}

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
				${/* Sized in the same units as what it is looking at. A pitched
				     grid's rows touch, so its window must count `cell` and not
				     `cell + GAP` — measured in one place and the content in
				     another, a two-row window quietly held three rows and there
				     was nothing left to scroll. */ ""}
				style=${windowed
					? { maxHeight: `${visible * (tight ? cell : cell + GAP)}px`, overflowY: "auto" }
					: null}
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

/* Where a beat begins, worked out from what the app declared rather than
 * assumed to be every fourth step.
 *
 * It has been every fourth step in every grid so far, which is exactly why it
 * was worth not writing down: 4/4 with a step to the sixteenth is a fact about
 * a rig, and this package is not allowed to know one (#1465). Three of the five
 * places that mark a beat derived it and two wrote down 4 — so a grid of twelve
 * over three beats would have had a note grid marking one column and its own
 * velocity lane marking another, which is the kind of disagreement nobody
 * reports because neither looks wrong on its own. */
const beatEvery = (steps, beats) => Math.max(1, Math.round(steps / Math.max(1, beats)));

/* Four colours across a bar, one to a beat, in the TR-808's own run.
 *
 * **This is the most recognisable thing a step sequencer does** and it is worth
 * a mark of its own: a person can count a bar on an 808 without reading a
 * number, because the sixteen buttons run red, orange, amber, bone in fours.
 * The faint tint on every fourth cell was doing the same job an order of
 * magnitude more quietly.
 *
 * Above the grid rather than on it, because it is a **mark and not a face**
 * (#2107): drawn on the cells it would be a second colour competing with the
 * one that says a step is on, and the reading of the pattern would suffer to
 * make the counting easier. As a strip it costs a few pixels and nothing else.
 *
 * A beat's width is `steps / beats` cells, whatever those numbers are — a grid
 * of twelve over three beats groups in fours as readily as sixteen over four,
 * and neither is written down here. */
function BeatStrip ({ steps, beats, tight }) {
	const per = beatEvery(steps, beats);

	return html`
		<div
			class=${`beats ${tight ? "tight" : ""}`}
			style=${{ gridTemplateColumns: `var(--label) repeat(${steps}, var(--cell))` }}
			aria-hidden="true"
		>
			<span class="beats-label"></span>
			${Array.from({ length: steps }, (_, step) => html`
				<i key=${`beat-${step}`} class=${["beat",
					Math.floor(step / per) % 2 ? "off" : "",
					step % (per * 4) === 0 ? "barline" : ""].filter(Boolean).join(" ")}></i>`)}
		</div>`;
}

function Grid ({ control, rows, steps, beats, weights, cells, drawn, kinds, visible, cell, pending, failed, onTap }) {
	/* A label column bounded by the viewport, then one column per step at
	   whatever size is set. The columns are that size exactly rather than at
	   least it: a person who asks for compact cells wants the space back for
	   something else, not the same grid stretched to fill the glass again. */
	const style = {
		gridTemplateColumns: `var(--label) repeat(${steps}, var(--cell))`,
	};

	return html`
		<${BeatStrip} steps=${steps} beats=${beats} />
		<${Window} rows=${rows.length} visible=${visible} cell=${cell}>
		<div class="grid" style=${style}>
			${rows.map((row) => html`
				<div class="row-label" key=${`label-${row}`} data-row=${row}>${row.replace(/_/g, " ")}</div>
				${Array.from({ length: steps }, (_, step) => {
					const path = `${control}/${row}/${step}`;
					const on = (cells[row] || []).includes(step);

					/* A step an algorithm put here this cycle. Drawn as a dot
					   rather than a face, because it is not one: nothing stores
					   it and it may be somewhere else next time round.
					
					   Tapping it needs no gesture of its own — the cell is off,
					   so an ordinary tap turns it on, and that *is* tracing it
					   into a permanent step.
					
					   **The dot stays once it has been traced**, and that is not
					   decoration: a generator that does not skip occupied steps
					   goes on firing there, so the step is now sounding twice.
					   Hiding the dot under the face would hide that. */
					const struck = ((drawn || {})[row] || {})[step];
					const ghost = struck !== undefined;

					/* **What put it there, not only that something did.** A
					   routed grid's notes and an algorithm's wore the same mark,
					   so Simon went looking for a generator behind a note the
					   route had contributed and found none. A route's note is
					   drawn square, because it is a note somebody wrote down on
					   another grid and squares are what a written note looks
					   like here; an invented one stays round. */
					const routed = ghost && kinds && kinds[struck.from] === "pattern";

					return html`
						<div
							key=${path}
							data-path=${path}
							class=${["cell", on ? "on" : "", ghost ? "ghost" : "",
								routed ? "routed" : "",
								pending.has(path) ? "pending" : "",
								failed.has(path) ? "failed" : "",
								step % beatEvery(steps, beats) === 0 ? "downbeat" : ""]
								.filter(Boolean).join(" ")}
							style=${ghost ? { "--struck": weightOf(struck.v, weights) } : null}
							onPointerDown=${(event) => { event.preventDefault(); onTap(path, !on); }}
						></div>`;
				})}
			`)}
		</div>
		<//>`;
}

/* The note values a grid can actually hold, and which of them make a grid.
 *
 * One table, read two ways. A **length** may be any of these; a **snap** may be
 * only those that divide a beat evenly, which is what makes a lattice — and
 * that filter is why no dotted value ever appears as a snap without anybody
 * having to say so. A value that does not come out as a whole number of
 * positions is not offered at all, so a grid keeping one position to a step is
 * honestly told it can snap to sixteenths and nothing finer.
 *
 * Written in beats because a beat is the only unit both ends already agree on:
 * the app declares `steps` and `beats`, and `divisions` says how finely a step
 * is kept. Everything else here is arithmetic. */
const NOTE_VALUES = [
	{ label: "1/4", beats: 1 },
	{ label: "1/8.", beats: 0.75 },
	{ label: "1/8", beats: 0.5 },
	{ label: "1/8T", beats: 1 / 3 },
	{ label: "1/16.", beats: 0.375 },
	{ label: "1/16", beats: 0.25 },
	{ label: "1/16T", beats: 1 / 6 },
	{ label: "1/32", beats: 0.125 },
	{ label: "1/32T", beats: 1 / 12 },
	{ label: "1/96", beats: 1 / 24 },
];

/* How many positions a note value is, or null where it is not a whole number of
 * them. Rounded before it is tested because a third of a beat cannot be written
 * exactly in binary: 1/3 * 24 is 7.999999999999999, and a test for wholeness
 * that believed that would drop every triplet from the list. */
function positionsOf (value, perBeat) {
	const exact = value.beats * perBeat;
	const whole = Math.round(exact);

	return whole >= 1 && Math.abs(exact - whole) < 1e-6 ? whole : null;
}

/* The values this grid can hold, each with its size in positions. */
function valuesFor (perBeat) {
	return NOTE_VALUES
		.map((value) => ({ ...value, positions: positionsOf(value, perBeat) }))
		.filter((value) => value.positions !== null);
}

/* The values that also tile a beat exactly, which is what a snap has to do. */
function snapsFor (perBeat) {
	return valuesFor(perBeat).filter((value) => perBeat % value.positions === 0);
}

/* Which note covers a position in a row, and where that note starts.
 *
 * A note is addressed by where it starts and drawn as a bar reaching past it,
 * so the ground under the rest of the bar holds no note of its own. Without
 * this a tap on the middle of a long note reads as a tap on empty ground and
 * places a second note underneath the first — which on a monophonic part
 * retriggers the envelope and cuts the long note short.
 *
 * **The bar is one thing on the glass, so it is one target** (#2107).
 *
 * Where two notes overlap the later start wins, which is the one drawn on top.
 * Nothing here decides whether an overlap should exist; it decides which note a
 * finger landing on the glass is pointing at. */
function noteAt (held, position) {
	let found = null;

	for (const [start, note] of Object.entries(held || {})) {
		const at = Number(start);
		const span = Math.max(1, note.length || 1);

		if (position >= at && position < at + span && (!found || at > found.at)) {
			found = { at, note, span };
		}
	}

	return found;
}

/* Round a position onto the snap lattice, never off the pattern. */
function snapped (position, unit, positions) {
	return Math.max(0, Math.min(positions - 1, Math.round(position / unit) * unit));
}

const DRAG_SLOP = 8;
/* How far a finger must travel before a press becomes a drag rather than a tap.
 * Below this it is a tap that wobbled, which on glass is most of them. */

/* A pitched pattern: one row per note, and a note that may start between steps.
 *
 * A note is drawn as a bar reaching rightwards from where it starts, which is
 * how every piano roll draws one and needs no explaining. Position is pitch, so
 * the line is read as a shape before any label is read.
 *
 * **A position is not always a step.** The app declares `divisions`, which is
 * how many places a note may start within one drawn cell, and everything here
 * counts in those. A grid that declares nothing gets one to a cell and is the
 * grid it always was.
 *
 * **A press acts on the finger landing and a drag acts on the release** (#2046,
 * still). Pressing empty ground places a note; pressing a note selects it, and
 * pressing one already selected and letting go takes it away. What a drag does
 * waits, because a move changes a note's address rather than one of its values
 * — it cannot be streamed the way an absolute set can, and a left edge dragged
 * is a move for exactly that reason. So a drag draws a **ghost**, which is a
 * mark showing the request in the ring's own idiom, and the face underneath
 * goes on showing what the sequencer actually holds until the release is
 * answered. It also wakes the composition loop once for a gesture rather than
 * once for every position crossed. */
function NoteGrid ({ name, rows, steps, beats, divisions, notes, cell, window: windowRows,
                    labels, unreachable, snap, selected, pending, failed, onSelect, onSet }) {
	const style = {
		gridTemplateColumns: `var(--label) repeat(${steps}, var(--cell))`,
	};

	const positions = steps * divisions;

	/* **A piano roll has no gaps, and that is the whole of the arithmetic.**
	 *
	 * A step grid is a drum machine and its cells are pads, spaced. A pitched
	 * grid is a piano roll and its cells are a lattice, touching — which is how
	 * Logic, Ableton and Reaper all draw one, and how Simon reads one.
	 *
	 * It is also why there is now a single number here where there were two. A
	 * step used to occupy the cell *and* the gap after it, so a position that
	 * crossed a boundary and a position inside a cell were measured differently
	 * — and getting that wrong put the 1/32 marks at 55% across a cell, which
	 * is where Simon found it. With no gap, a position is a position: `cell /
	 * divisions`, everywhere, and the two measures cannot disagree because
	 * there is only one. */
	const unit = cell / divisions;

	const drag = useRef(null);

	/* **Kept twice, on purpose.** The state draws it; the ref decides with it.
	   A handler closes over the state as it was when that render attached it,
	   so a move and a release in the same frame left `finish` reading `null` and
	   the gesture asking for nothing — a note drawn out and let go quickly kept
	   the length it was placed at. Latent since the drag was written and only
	   ever surfaced by making the page a frame faster. */
	const wanted = useRef(null);
	const [ghost, setGhost] = useState(null);

	const shade = (next) => { wanted.current = next; setGhost(next); };

	/* One drawn cell at each end, so every grip is a full row across as the
	   target rule demands — and both grips plus the middle need three cells
	   between them before any of them can be. Below that the whole note moves
	   and nothing resizes, which is Simon's call: a short note is far more
	   often in the wrong place than the wrong length. */
	const grip = divisions;
	const zoneOf = (span, offset) => {
		if (span < 3 * divisions) return "move";

		if (offset < grip) return "start";

		return offset >= span - grip ? "end" : "move";
	};

	const positionIn = (event, step) => {
		const box = event.currentTarget.getBoundingClientRect();
		const within = Math.floor(((event.clientX - box.left) / box.width) * divisions);

		return step * divisions + Math.max(0, Math.min(divisions - 1, within));
	};

	const begin = (event, row, step) => {
		event.preventDefault();

		const at = positionIn(event, step);
		const put = snapped(at, snap, positions);

		/* **Where the finger landed, or where the snap would put a note** —
		   either counts as pressing an existing one.
		
		   `snapped` rounds, so it can round *up* onto a position where a note
		   already starts. Asking only about the landing then read as empty
		   ground, and placing there rewrote that note's length with the current
		   snap: the `true` set is a no-op on the app, but the `/length` set
		   beside it is not. Reachable on a grid keeping six positions to a step
		   — press position 5 with a snap of 6 and the note at 6 is shortened by
		   somebody who aimed at the gap before it. */
		const found = noteAt(notes[row], at) || noteAt(notes[row], put);

		event.currentTarget.setPointerCapture(event.pointerId);

		if (!found) {
			/* Placed on the landing, at the snap's own length, and selected so
			   the length values below act on what was just drawn. */
			onSet(`${name}/${row}/${put}`, true);
			onSet(`${name}/${row}/${put}/length`, snap);
			onSelect({ row, at: put });

			drag.current = { pointer: event.pointerId, kind: "draw", row, at: put,
				span: snap, velocity: null, x: event.clientX, y: event.clientY, moved: false };
			return;
		}

		const already = selected && selected.row === row && selected.at === found.at;

		if (!already) onSelect({ row, at: found.at });

		drag.current = { pointer: event.pointerId, kind: zoneOf(found.span, at - found.at),
			row, at: found.at, span: found.span, velocity: found.note.velocity,
			x: event.clientX, y: event.clientY, moved: false, already };
	};

	const during = (event) => {
		const held = drag.current;

		if (!held || held.pointer !== event.pointerId) return;

		const dx = event.clientX - held.x;
		const dy = event.clientY - held.y;

		if (!held.moved && Math.abs(dx) < DRAG_SLOP && Math.abs(dy) < DRAG_SLOP) return;

		held.moved = true;

		const across = Math.round(dx / unit);

		if (held.kind === "move") {
			const down = Math.round(dy / controlRow(cell));
			const where = rows.indexOf(held.row);

			shade({
				row: rows[Math.max(0, Math.min(rows.length - 1, where + down))],
				at: snapped(held.at + across, snap, positions - held.span + 1),
				span: held.span,
			});
			return;
		}

		if (held.kind === "start") {
			const edge = snapped(held.at + across, snap, positions);
			const stop = held.at + held.span;

			if (edge >= stop) return;

			shade({ row: held.row, at: edge, span: stop - edge });
			return;
		}

		/* "end" and "draw" are the same gesture: the right edge follows the
		   finger and the note keeps where it starts. */
		const edge = snapped(held.at + held.span + across, snap, positions + 1);

		shade({ row: held.row, at: held.at, span: Math.max(snap, edge - held.at) });
	};

	const finish = (event) => {
		const held = drag.current;

		if (!held || held.pointer !== event.pointerId) return;

		const want = wanted.current;

		drag.current = null;
		shade(null);

		if (!held.moved) {
			/* A tap. The first selects — which the press already did — and a
			   second on a note already selected takes it away. Drawing a note
			   is never a removal, however briefly the finger stayed. */
			if (held.already && held.kind !== "draw") {
				onSet(`${name}/${held.row}/${held.at}`, false);
				onSelect(null);
			}

			return;
		}

		if (!want) return;

		if (want.row === held.row && want.at === held.at) {
			if (want.span !== held.span) onSet(`${name}/${held.row}/${held.at}/length`, want.span);

			return;
		}

		/* The address changed, so this is a move however it was grabbed — and a
		   note is addressed by where it starts, so there is no set that says
		   "the same note, elsewhere". Taken away and put back, oldest first so
		   a monophonic part cannot clear the note being moved on its way past.
		   Four frames for a whole gesture, and each of them absolute. */
		onSet(`${name}/${held.row}/${held.at}`, false);
		onSet(`${name}/${want.row}/${want.at}`, true);
		onSet(`${name}/${want.row}/${want.at}/length`, want.span);

		if (held.velocity != null) {
			onSet(`${name}/${want.row}/${want.at}/velocity`, held.velocity);
		}

		onSelect({ row: want.row, at: want.at });
	};

	const cancel = (event) => {
		if (drag.current && drag.current.pointer === event.pointerId) {
			drag.current = null;
			shade(null);
		}
	};

	/* Subdivision marks, drawn only while they can be told apart. Below about
	   six pixels a lattice of them is a grey wash rather than a grid, and a mark
	   nobody can resolve is a mark that says nothing — so the cell keeps its own
	   edges and the snap goes on working unannounced. They are marks and never
	   targets: read, never hit (#2107). */
	const subs = snap < divisions && snap * unit >= 6;

	/* A bar's geometry, in the lattice's own pixels.
	
	   **A position is a fraction of the cell, and the cell alone.** This once
	   said "the cell *and its gap*", which was true of a step grid and never of
	   this one: a pitched grid's cells touch, because a piano roll's ground is
	   continuous and a note crossing a boundary must not appear to stop and
	   start again. `unit` is the cell over the divisions and nothing else, which
	   is what makes this one mapping with no special case for a note that ends
	   on a boundary — there is no gap for it to reach into. The subdivision
	   marks are spaced by the same number, so the two cannot disagree. */
	const barStyle = (at, span, step) => ({
		left: `${(at - step * divisions) * unit}px`,
		width: `${span * unit}px`,
	});

	const per = beatEvery(steps, beats);

	return html`
		<${BeatStrip} steps=${steps} beats=${beats} tight />
		<${Window} rows=${rows.length} visible=${windowRows} cell=${cell} tight>
		<div class="grid notes" style=${style}>
			${rows.map((row) => html`
				${/* **The pitch it sounds, not the pitch it was drawn at** (#2144).
				     Transposition moves the sound and the labels follow it, which
				     is the whole of what keeps the glass honest — and the panel
				     cannot work these out, because it knows a row is called `C2`
				     and nothing else. The app hands them over.

				     A row marked unreachable is one the instrument will not sound
				     at this offset: a Minitaur ignores anything above note 72 and
				     goes *silent* rather than wrong, so without this the notes are
				     still drawn, still lit, and simply absent from the music. */ ""}
				<div
					class=${`row-label ${(unreachable || []).includes(row) ? "unreachable" : ""}`}
					key=${`label-${row}`} data-row=${row}
				>${(labels || {})[row] || row}</div>
				${Array.from({ length: steps }, (_, step) => {
					const path = `${name}/${row}/${step * divisions}`;
					const note = (notes[row] || {})[String(step * divisions)];

					/* Every note starting anywhere inside this cell, not only one
					   starting exactly on it: with more than one division a cell
					   holds several places a note may begin. */
					const beginning = Object.entries(notes[row] || {})
						.map(([start, held]) => ({ at: Number(start), note: held }))
						.filter((one) => Math.floor(one.at / divisions) === step);

					const shade = ghost && ghost.row === row
						&& Math.floor(ghost.at / divisions) === step ? ghost : null;

					const asked = noteAt(notes[row], step * divisions);
					const owner = asked ? `${name}/${row}/${asked.at}` : path;

					return html`
						<div
							key=${path}
							data-path=${path}
							class=${["cell",
								pending.has(owner) && !asked ? "pending" : "",
								failed.has(owner) && !asked ? "failed" : "",
								step % per === 0 ? "downbeat" : ""].filter(Boolean).join(" ")}
							onPointerDown=${(event) => begin(event, row, step)}
							onPointerMove=${during}
							onPointerUp=${finish}
							onPointerCancel=${cancel}
						>
							${subs && html`
								<i class="subs" style=${{
									backgroundSize: `${snap * unit}px 100%`,
									backgroundPositionX: `${-((step * divisions) % snap) * unit}px`,
								}}></i>`}
							${beginning.map((one) => html`
								<div
									key=${`note-${one.at}`}
									class=${["note",
										selected && selected.row === row && selected.at === one.at
											? "chosen" : "",
										pending.has(`${name}/${row}/${one.at}`) ? "pending" : "",
										failed.has(`${name}/${row}/${one.at}`) ? "failed" : "",
										one.note.length >= 3 * divisions ? "gripped" : ""]
										.filter(Boolean).join(" ")}
									style=${barStyle(one.at, Math.max(1, one.note.length || 1), step)}
								></div>`)}
							${shade && html`
								<div class="note asked"
									style=${barStyle(shade.at, shade.span, step)}></div>`}
						</div>`;
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
function VelocityLane ({ name, rows, steps, beats, divisions, notes, range, cell, tight, onSet }) {
	const style = {
		gridTemplateColumns: `var(--label) repeat(${steps}, var(--cell))`,
		height: `${LANE_CELLS * cell + (LANE_CELLS - 1) * GAP}px`,
	};

	const [low, high] = range;
	const holding = useRef(null);

	/* The note beginning in this drawn cell, wherever inside it that is: with
	   more than one division a column is several places a note may start, and
	   looking one up by the cell's own number would find only the notes that
	   happen to sit on a step. The earliest wins, so a column reads left to
	   right like everything else. */
	const at = (step) => {
		let found = null;

		for (const row of rows) {
			for (const [start, note] of Object.entries(notes[row] || {})) {
				const put = Number(start);

				if (Math.floor(put / divisions) === step && (!found || put < found.at)) {
					found = { row, note, at: put };
				}
			}
		}

		return found;
	};

	const set = (event, step) => {
		const found = at(step);

		if (!found) return;

		const box = event.currentTarget.getBoundingClientRect();
		const part = 1 - Math.min(1, Math.max(0, (event.clientY - box.top) / box.height));
		const wanted = Math.round(low + part * (high - low));

		if (wanted === found.note.velocity) return;

		onSet(`${name}/${found.row}/${found.at}/velocity`, wanted);
	};

	return html`
		<div class=${`lane ${tight ? "tight" : ""}`} style=${style}>
			<div class="row-label">velocity</div>
			${Array.from({ length: steps }, (_, step) => {
				const found = at(step);
				const height = found ? Math.max(4, ((found.note.velocity - low) / (high - low)) * 100) : 0;

				return html`
					<div
						key=${`vel-${step}`}
						data-velocity=${step}
						class=${`weight ${step % beatEvery(steps, beats) === 0 ? "downbeat" : ""}`}
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

/* A pitched pattern's own settings, under the grid they belong to.
 *
 * Two rows, and the height does not change with what is selected: a strip that
 * appeared and vanished would move everything below it every time a note was
 * touched, on a surface where the thing below it is another instrument.
 *
 * **Snap first, because it governs every gesture above.** The values offered
 * are the ones this grid can hold and that tile a beat exactly — a grid keeping
 * one position to a step is honestly offered sixteenths alone, rather than a
 * precision it has nowhere to put.
 *
 * **Then the selected note's length, by name.** The finest values are two or
 * three pixels of bar, so an edge grip can never reach them however carefully
 * it is drawn; a dotted eighth is not something a drag arrives at either. A
 * musician picks the value, which is the thing they were thinking of anyway. */
function NoteControls ({ values, snaps, snap, onSnap, selected, note, onLength, onRemove,
                        transpose, transposeRange, onTranspose }) {
	/* **Two buttons and a readout, not a picker** — which is what every piece of
	 * hardware that transposes offers, because a performer's hand does not choose
	 * from a list. The octave pair is there because walking an octave one
	 * semitone at a time is twelve taps at the worst possible moment.
	 *
	 * The readout is a mark rather than a target: it says where the pattern is
	 * and cannot be pressed, so there is nothing to hit by accident while
	 * reading it (#2107). */
	const [low, high] = transposeRange || [-24, 24];
	const shift = (by) => onTranspose(Math.min(high, Math.max(low, (transpose || 0) + by)));

	return html`
		<div class="note-controls">
			${onTranspose && html`
				<div class="note-row">
					<span class="row-label">transpose</span>
					${[-12, -1].map((by) => html`
						<button key=${`t${by}`} class="offer" data-transpose=${by}
							onPointerDown=${(event) => { event.preventDefault(); shift(by); }}
						>${by}</button>`)}
					<span class="reading" data-transpose="now">${
						(transpose || 0) > 0 ? `+${transpose}` : `${transpose || 0}`}</span>
					${[1, 12].map((by) => html`
						<button key=${`t${by}`} class="offer" data-transpose=${`+${by}`}
							onPointerDown=${(event) => { event.preventDefault(); shift(by); }}
						>+${by}</button>`)}
				</div>`}
			<div class="note-row">
				<span class="row-label">snap</span>
				${snaps.map((value) => html`
					<button
						key=${`snap-${value.label}`}
						class=${`offer ${value.positions === snap ? "on" : ""}`}
						data-snap=${value.label}
						onPointerDown=${(event) => { event.preventDefault(); onSnap(value.positions); }}
					>${value.label}</button>`)}
			</div>
			<div class=${`note-row ${note ? "" : "idle"}`}>
				<span class="row-label">note</span>
				${note
					? html`
						${values.map((value) => html`
							<button
								key=${`len-${value.label}`}
								class=${`offer ${value.positions === note.length ? "on" : ""}`}
								data-length=${value.label}
								onPointerDown=${(event) => {
									event.preventDefault();
									onLength(value.positions);
								}}
							>${value.label}</button>`)}
						<span class="spacer"></span>
						<button
							class="clear"
							onPointerDown=${(event) => { event.preventDefault(); onRemove(); }}
						>remove</button>`
					: html`<span class="hint">tap a note to set its length</span>`}
			</div>
		</div>`;
}

/* A pitched pattern and everything that acts on it.
 *
 * The grid, the velocity lane and the settings strip are one control on the
 * glass and share two pieces of state — which note is selected, and what the
 * gestures snap to — so they are one component here rather than three siblings
 * threading state through the page.
 *
 * Snap starts at one drawn cell, which is what every gesture did before there
 * was a choice. */
function NoteBlock ({ name, control, notes, cell, pending, failed, onSet }) {
	const divisions = Math.max(1, control.divisions || 1);
	const steps = control.steps;
	const beats = control.beats || 4;

	/* Positions to a beat, which is what names a note value. Derived rather
	   than declared: the app already says how many steps it has, how many beats
	   they make and how finely a step is kept, and a fourth number that had to
	   agree with the other three is a fourth number that can disagree. */
	const perBeat = (steps * divisions) / beats;

	const values = useMemo(() => valuesFor(perBeat), [perBeat]);
	const snaps = useMemo(() => snapsFor(perBeat), [perBeat]);

	const hasWeights = Array.isArray(control.velocity_range)
		&& control.velocity_range.length === 2;

	const [snap, setSnap] = useState(divisions);
	const [selected, setSelected] = useState(null);

	/* Read back rather than remembered, so a note removed from another panel
	   takes the selection with it instead of leaving buttons acting on nothing. */
	const note = selected ? (notes[selected.row] || {})[String(selected.at)] || null : null;

	return html`
		<${NoteGrid} name=${name} rows=${control.rows} steps=${steps} beats=${beats}
			divisions=${divisions}
			notes=${notes} cell=${cell} window=${control.visible_rows}
			labels=${notes.labels} unreachable=${notes.unreachable}
			snap=${snap} selected=${selected} pending=${pending} failed=${failed}
			onSelect=${setSelected} onSet=${onSet} />
		${/* **Drawn only where the app said what a weight means.** The lane's
		     whole job is to show one, and it read `|| [1, 127]` — a MIDI number
		     invented by the panel for an app that had not offered one, which
		     would draw every note somewhere on a scale nobody declared. A grid
		     that says nothing gets no lane, the same way one that declares no
		     divisions is honestly offered sixteenths and nothing finer. */ ""}
		${hasWeights && html`
			<${VelocityLane} name=${name} rows=${control.rows} steps=${steps} beats=${beats}
				divisions=${divisions} tight
				cell=${cell} notes=${notes} range=${control.velocity_range} onSet=${onSet} />`}
		<${NoteControls} values=${values} snaps=${snaps} snap=${snap} onSnap=${setSnap}
			selected=${selected} note=${note}
			transpose=${notes.transpose} transposeRange=${control.transpose_range}
			onTranspose=${control.transpose_range
				? (semitones) => onSet(`${name}/transpose`, semitones)
				: null}
			onLength=${(length) => onSet(`${name}/${selected.row}/${selected.at}/length`, length)}
			onRemove=${() => {
				onSet(`${name}/${selected.row}/${selected.at}`, false);
				setSelected(null);
			}} />`;
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

/* How wide to draw a note that was played this hard, as a share of the cell.
 *
 * Simon: "ghost fills appear the same as full-on hits. This must change." They
 * are not the same and never were — a ghost is a quiet note by its whole nature,
 * and drawing it at the weight of a full hit says the opposite of what it is.
 *
 * Radius rather than opacity, because he is right that it reads on both a circle
 * and a square, and because a faint mark on glass at an angle in a dark room is
 * a mark that is not there. A floor of a third, so the quietest note is still
 * something rather than nothing: this says *how hard*, and a note that cannot be
 * seen has stopped saying anything at all. */
const weightOf = (velocity, range) => {
	/* **The scale is the app's**, and without one there is nothing to say. This
	   divided by a hard-coded 127 — a MIDI number, in a package whose own
	   `controls.py` says it carries no MIDI at all and leaves what a value
	   means to the composition. An app that declares its range gets marks drawn
	   in proportion to it; one that does not gets marks all the same size,
	   because "how hard" is a question this panel then cannot answer and must
	   not appear to. */
	if (!range || range.length !== 2) return "1.000";

	const [low, high] = range;
	const span = high - low;

	if (!(span > 0)) return "1.000";

	const held = Math.min(high, Math.max(low, Number(velocity) || low));

	return (0.34 + 0.66 * ((held - low) / span)).toFixed(3);
};

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
	const [sent, setSent] = useState(null);
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

	/* Both a choice and a choices open the same menu in the same place, so the
	   placement is written once. Two copies of this drifted apart in an earlier
	   life of the settings panel and only the one being looked at was fixed. */
	const menuStyle = () => ({
		left: `${where.left}px`,
		minWidth: `${where.minWidth}px`,
		maxHeight: `${where.maxHeight}px`,
		...(where.top !== undefined
			? { top: `${where.top}px` }
			: { bottom: `${where.bottom}px` }),
	});

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
		/* **The same toggle as everywhere else**, which #2107 has required since
		   it was written and which this quietly was not: a settings switch was
		   a button of its own, with its own markup and its own idea of what on
		   looks like, and the two only diverged far enough to notice once the
		   other one became a rocker. One component, one sentence. */
		return html`<${Toggle} on=${held} title=${field.label || field.name} onFlip=${onSet} />`;
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
					class=${`picker ${open ? "open" : ""}`}
					onPointerDown=${(event) => {
						event.preventDefault();
						open ? setOpen(false) : show();
					}}
				>${chosen ? chosen.label || chosen.value : "choose"}<i>▾</i></button>

				${open && where && html`
					${/* **One framed control, and it says so.** Its rows carry no
					     edge of their own, on the same principle as a rocker's
					     two ends: the frame is what a person finds, and a box
					     inside a box reads worse. The rocker declares that with
					     a role and these did not, so the rule had to be a list
					     of class names in a test — and a list is what drifts. */ ""}
					<div
						role="group"
						class="options"
						style=${menuStyle()}
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

	if (field.kind === "choices") {
		const options = field.options || [];
		const chosen = Array.isArray(held) ? held : [];

		/* **Several of a pool, where a choice is one of it.** Every chord and
		   melody writer in Subsequence's catalogue asks for one, and until the
		   panel could draw it twenty-two of thirty-three generators arrived with
		   a parameter missing — not a random two thirds, but exactly the ones
		   that write more than a single voice (#2150).

		   Picking is a toggle rather than a replacement, and the order kept is
		   the order they were picked: the pitches of a chord are not a set, and
		   a generator handed a root first is entitled to use that. */
		const toggle = (value) => onSet(
			chosen.includes(value)
				? chosen.filter((one) => one !== value)
				: [...chosen, value]);

		const labelOf = (value) => {
			const option = options.find((one) => one.value === value);

			return option ? option.label || option.value : value;
		};

		const option = (value, label) => html`
			<button
				key=${value}
				class=${chosen.includes(value) ? "here" : ""}
				onPointerDown=${(event) => { event.preventDefault(); toggle(value); }}
			>${label}</button>`;

		if (options.length <= CHOICE_BUTTONS) {
			return html`
				<div class="choices">
					${options.map((one) => option(one.value, one.label || one.value))}
				</div>`;
		}

		/* **The menu does not close on a pick**, because picking several and
		   shutting after the first would be a choice wearing a plural. It closes
		   the way it opened, on its own trigger — which is what the open state on
		   the picker is already saying. */
		return html`
			<div class="menu">
				<button
					ref=${trigger}
					class=${`picker ${open ? "open" : ""}`}
					onPointerDown=${(event) => {
						event.preventDefault();
						open ? setOpen(false) : show();
					}}
				>${chosen.length === 0
					? "choose"
					: chosen.length <= 2
						? chosen.map(labelOf).join(", ")
						: `${labelOf(chosen[0])} +${chosen.length - 1}`}<i>▾</i></button>

				${open && where && html`
					<div role="group" class="options" style=${menuStyle()}>
						${options.map((one) => option(one.value, one.label || one.value))}
					</div>`}
			</div>`;
	}

	if (field.kind === "action") {
		const options = field.options || [];

		/* **A control that does something and holds nothing** (#2179).
		 *
		 * Every other control here draws a value. This one must not, because the
		 * thing it sets cannot be read back: a Matriarch's voicing is a
		 * front-panel switch as well as a control change, so any selection shown
		 * here would be wrong the moment a hand moved that switch, and a panel
		 * arriving late would be told a confident lie (#2172).
		 *
		 * So no button is ever marked as chosen. What a press gets instead is
		 * the vocabulary this panel already uses for an attempt that leaves no
		 * state behind — a fill that marks the press and decays — rather than
		 * the ring, which promises that a face is about to change and is a
		 * promise this control can never keep. Without any answer at all a
		 * control with no state reads as a dead one, and under #2107 a control
		 * that looks broken is broken. */
		const fire = (value) => {
			onSet(value);
			setSent(value);
			setTimeout(() => setSent((held) => (held === value ? null : held)), ACTION_FLASH);
		};

		return html`
			<div class="actions">
				${options.map((option) => html`
					<button
						key=${option.value}
						class=${option.value === sent ? "sent" : ""}
						onPointerDown=${(event) => { event.preventDefault(); fire(option.value); }}
					>${option.label || option.value}</button>`)}
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
					<div class="setting" key=${field.name} data-field=${field.name}
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
					<${Toggle}
						on=${!layer.bypassed}
						title=${layer.bypassed ? "bring this back" : "silence this"}
						onFlip=${() => send(layers.map((one) =>
							one.id === layer.id ? { ...one, bypassed: !one.bypassed } : one))} />
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
				</div>

				${offered
					? offered.parameters.map((field) => [
						html`
							<div class="row-label" key=${`label-${field.name}`}>
								${field.label || field.name}
							</div>`,
						html`
							<div class="setting" key=${field.name} data-field=${field.name}
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


/* One toggle, everywhere something is on or off.
 *
 * Simon: "Can we enable a 'toggle' control universally, for on/off?" — after
 * finding a generator's bypass and a pattern's mute drawn at different weights
 * in the same footer. They were two buttons written in two places that happened
 * to mean the same thing, which is how they came to look different.
 *
 * There is one now, and it is the only way to draw one. A switch on a line
 * cannot use it — SVG has no button — but it says the same sentence, which is
 * the half that has to be identical: filled is sounding, outlined is not. */
function Toggle ({ on, title, onFlip }) {
	/* Two ends, and each one **sets** rather than flips. A rocker on a machine
	   is pressed on the side you want, and that is worth more here than the
	   word "toggle" suggests: a set is absolute, so pressing ON twice is ON,
	   where a flip pressed twice is where you started. On glass, with no
	   feedback but the panel itself, that difference is the whole of it.

	   It also means a tap is unambiguous where a slide switch's was not — Simon
	   read a control that moved under his finger as one that had not
	   responded. */
	const end = (want, word) => html`
		<button
			type="button"
			class=${`end ${want ? "yes" : "no"}`}
			aria-pressed=${on === want ? "true" : "false"}
			onPointerDown=${(event) => {
				event.preventDefault();
				if (on !== want) onFlip(want);
			}}
		>${word}</button>`;

	return html`
		<div class=${`switch ${on ? "on" : ""}`} role="group" title=${title}
			data-on=${on ? "true" : "false"}>
			${end(false, "off")}${end(true, "on")}
		</div>`;
}


/* Lucide's paths, copied rather than depended on.
 *
 * **Why the paths and not the package.** Every serious icon set is permissive —
 * Lucide is ISC, Phosphor and Tabler MIT, and none of them wants attribution in
 * the interface. What separates them here is that Lucide is drawn on a 24-unit
 * grid with a uniform 2-unit stroke, so a glyph is *stroke geometry*: it scales
 * with the cell the way #2107 requires a mark to, where an icon font or a sprite
 * sheet cannot. And a dozen glyphs are not a dependency. Copied in, they cost
 * the panel no fetch on a Pi, cannot drift against a version, and cannot fail
 * to load — which for a surface with no keyboard is the difference between a
 * control and a blank square.
 *
 * The licence text lives in `licences/lucide.txt` because ISC asks for that and
 * nothing else. Add a glyph by pasting its path here, not by adding a package.
 */
const ICONS = {
	close: "M18 6 6 18M6 6l12 12",
	add: "M5 12h14M12 5v14",
	send: "M5 12h14M13 6l6 6-6 6",
	clear: "M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
	play: "m7 4 13 8-13 8z",
	pause: "M7 4h3.5v16H7zM13.5 4H17v16h-3.5z",
};

/* One glyph, sized by the surface it sits on rather than by itself — the size
   rule applies to a mark as much as to a control (#2107). `currentColor` so a
   purpose changing a control's colour changes its icon with it, and
   `aria-hidden` because the button around it carries the name. */
function Icon ({ of, filled }) {
	return html`
		<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"
			fill=${filled ? "currentColor" : "none"}
			stroke=${filled ? "none" : "currentColor"}
			stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
			<path d=${ICONS[of]} />
		</svg>`;
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
function Footer ({ onAdd, adds, onSend, onClear, live, onLive, outlet }) {
	if (!onAdd && !onSend && !onClear && onLive === undefined) return null;

	return html`
		<footer class="part-foot">
			${/* A mute, in the sense a mixer means it. First, because silencing a
			     thing is the action a hand reaches for soonest and the one that
			     has to be found without reading. */ ""}
			${onLive !== undefined && html`
				<span class="legend">live</span>
				<${Toggle} on=${live}
					title=${live ? "silence this" : "bring this back"} onFlip=${onLive} />`}
			${/* **"Add a contribution" was ours, not a musician's.** Simon: not an
			     intuitive way to connect items. A *source* is what the protocol
			     already calls the thing being added, what a mixer calls what
			     feeds a channel, and what a patchbay calls the end you take a
			     cable from — so it is the word already in use at both ends, and
			     the shortest one that is true of a generator and a routed grid
			     alike. It is "add generator" now: a cable dragged between two
			     blocks is how a route is made, so this only ever adds the one
			     thing. */ ""}
			${onAdd && html`
				<button
					class="offer add"
					onPointerDown=${(event) => { event.preventDefault(); onAdd(); }}
				><${Icon} of="add" />${adds}</button>`}
			${onSend && html`
				<button
					class="offer send"
					onPointerDown=${(event) => { event.preventDefault(); onSend(); }}
				><${Icon} of="send" />send to…</button>`}
			<span class="spacer"></span>
			${/* **The outlet: take a cable from here and drop it on the block it
			     should feed.** Simon's, and it is the gesture a person who has
			     patched anything already has — where "send to…" beside it asks
			     the same question as a list. That list stays, because two blocks
			     on different pages cannot be dragged between and a person should
			     never be stranded; the cable is the near way and the list is the
			     one that always works. */ ""}
			${outlet && html`
				<span class="legend">out</span>
				<button
					class="outlet"
					title="drag a cable to the pattern this should feed"
					onPointerDown=${outlet.onStart}
					onPointerMove=${outlet.onMove}
					onPointerUp=${outlet.onEnd}
					onPointerCancel=${outlet.onEnd}
				><i></i></button>`}
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
function Part ({ title, about, name, flavour, at, cell, depth, locked, takes, offers, onMove, onRaise, onHold, onSettled, onTouch, onClose, footer, children }) {
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
			class=${`part ${flavour || ""}`} data-part=${name} data-takes=${takes || null}
			data-offers=${offers || null}
			style=${place}
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
			>
				<b>${title || name.replace(/_/g, " ")}</b>
				<span class="spacer"></span>
				${/* Whatever the app thought was worth knowing at a glance — a MIDI
				     channel, the instrument's full name. Drawn and nothing else:
				     this package is not allowed to know any of them, so a panel
				     that worked them out would be a panel that knew what a rig
				     looked like (#1465). The name keeps its size and these give
				     way, because the name is what a block is found by. */ ""}
				${(about || []).length > 0 && html`
					<span class="about">
						${about.map((fact) => html`
							<span key=${fact.label}>
								<i>${fact.label}</i>
								<em>${fact.value}</em>
							</span>`)}
					</span>`}
				${/* Top right, where every windowed system has put it for forty
				     years — Simon's point, and it costs nothing to be where a
				     hand already goes. It was among the controls, which put
				     "remove this whole thing" beside "nudge it up one".
				
				     The propagation stops here or the title bar's drag begins
				     under the same finger. */ ""}
				${onClose && html`
					<button
						class="close" title="remove" aria-label="remove"
						onPointerDown=${(event) => {
							event.preventDefault();
							event.stopPropagation();
							onClose();
						}}
					><${Icon} of="close" /></button>`}
			</header>
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

/* Where a line should start and end.
 *
 * **Level with the row it acts on, when it acts on one.** Simon asked for it and
 * the reason is the whole point of drawing lines at all: a generator that writes
 * the snare should arrive at the snare, not at the middle of a pattern that has
 * ten rows in it. It costs the freedom to leave by the top or the bottom — a
 * line level with a row has to come in from a side — and that is a price he
 * named himself when asking.
 *
 * A contribution that names no row keeps the nearest pair of side midpoints. A
 * generic generator feeds the pattern rather than a part of it, and pointing at
 * one of its rows would be a claim that is not true.
 *
 * The row's height is clamped inside the block, because a pattern taller than
 * its window scrolls: a row that is out of view would otherwise be pointed at
 * somewhere off the block entirely. */
function anchorsFor (from, to, level, anchor, slot = 0, slots = 1) {
	if (level === null) {
		const leaving = sidesOf(from);
		const arriving = sidesOf(to);
		let best = null;

		for (let one = 0; one < leaving.length; one += 1) {
			for (let two = 0; two < arriving.length; two += 1) {
				const away = Math.hypot(
					arriving[two].x - leaving[one].x, arriving[two].y - leaving[one].y);

				if (!best || away < best.away) best = { one, two, away };
			}
		}

		return {
			a: leaving[best.one], b: arriving[best.two],

			/* Which side of which block each end came to rest on. Nothing here
			   uses it; `fanTerminals` does, and it cannot work the answer out
			   afterwards from a point alone — a point on a corner belongs to
			   two sides and a point on an overlapped block to none. */
			ends: { a: best.one, b: best.two },
		};
	}

	/* Whichever pair of facing sides is shorter, which for two blocks side by
	   side is the obvious one and for two that overlap is at least consistent. */
	const leftward = from.x + from.w / 2 <= to.x + to.w / 2;
	const held = Math.min(
		Math.max(level, to.y + anchor), Math.max(to.y + anchor, to.y + to.h - anchor));

	/* **Several generators can land on one voice**, and until now they landed on
	   one point and merged — the same fault that once made three arrowheads a
	   smudge at a block's edge. They queue outward from the block instead, one
	   lug each, and **left to right is the order they run in**: the stack's
	   order stops being a number in a window and becomes something visible on
	   the pattern it belongs to, with no new control at all. */
	const out = (slots - 1 - slot) * anchor * 2.6;

	return {
		a: { x: leftward ? from.x + from.w : from.x, y: from.y + from.h / 2 },
		b: { x: leftward ? to.x - out : to.x + to.w + out, y: held },

		/* The source end leaves by the middle of a side like any other line, so
		   it joins whatever fan is on that edge. The destination end is already
		   spread — outward, by its lug — and must not be moved a second time by
		   a rule that spreads along instead. */
		ends: { a: leftward ? 1 : 3, b: null },
	};
}

/* Several cables meeting one block edge, spread along it.
 *
 * Every end was the middle of a side, so a grid feeding three patterns put
 * three plugs on one point. That was tolerable while a cable could only be
 * looked at; once either end could be dragged (#2119) it stopped being: two
 * fittings on the same spot are one fitting as far as a finger is concerned,
 * and which cable came away was whichever the document happened to hit first.
 *
 * Simon described the answer before the problem was filed — "the first is
 * connected, it is simply in the centre of the edge; when I add a second, there
 * are two adjacent patch points, equidistant on the edge". So terminals are not
 * drawn until a cable needs one, and the set of them stays centred on the edge
 * as it grows, which is what makes a second cable *push* the first aside rather
 * than appear beside it in some vacant socket.
 *
 * **Along the edge, not outward from it.** A generator's lugs queue outward
 * from the block (`anchorsFor`), because they all arrive at one voice's level
 * and moving them along would be a lie about which row they write. A route
 * arrives at the block rather than at a row, so its edge is free — and the two
 * fans being perpendicular is worth having, because it keeps the two kinds of
 * connection telling themselves apart at yet another glance.
 *
 * **Order means something at a destination and nothing at a source.** Routes
 * into one pattern are stack layers of that pattern and run in order, so they
 * are laid out in it; a grid sends the same notes down every cable it feeds, so
 * at the source end the order is chosen to keep the cables from crossing —
 * sorted by where the far block sits along the same axis.
 *
 * **A fan that will not fit stops offering targets.** The pitch is clamped to
 * the edge, and where that leaves a terminal less than a control row of its
 * own, the whole cable's fittings become marks — the same trade #2107 makes on
 * a cable too short to hold three of them, for the same reason. */
function fanTerminals (laid, inset, row) {
	const groups = new Map();

	laid.forEach((line, order) => {
		for (const end of ["a", "b"]) {
			const side = line.ends[end];

			if (side === null || side === undefined) continue;

			const key = `${end === "a" ? line.from : line.to}\u0000${side}`;

			if (!groups.has(key)) groups.set(key, []);

			groups.get(key).push({ line, end, order });
		}
	});

	for (const held of groups.values()) {
		const first = held[0];
		const side = first.line.ends[first.end];

		/* A left or a right edge runs down the page and a top or a bottom one
		   across it, which is the only thing the rest of this needs to know. */
		const upright = side === 1 || side === 3;
		const box = first.end === "a" ? first.line.boxes.from : first.line.boxes.to;

		const along = (one) => {
			const far = one.end === "a" ? one.line.boxes.to : one.line.boxes.from;

			return upright ? far.y + far.h / 2 : far.x + far.w / 2;
		};

		held.sort((one, two) => {
			/* A mixed edge — a block sending and receiving on the same side —
			   is rare and has to be settled somehow: what arrives comes first,
			   so a destination's order stays the stack's whatever else is
			   sharing the edge with it. */
			if ((one.end === "b") !== (two.end === "b")) return one.end === "b" ? -1 : 1;

			return one.end === "b" ? one.order - two.order : along(one) - along(two);
		});

		const many = held.length;
		const want = row * 1.3;
		const usable = Math.max(0, (upright ? box.h : box.w) - inset * 2);
		const pitch = many > 1 ? Math.min(want, usable / (many - 1)) : want;

		held.forEach((one, place) => {
			const shift = (place - (many - 1) / 2) * pitch;
			const at = one.line[one.end];

			one.line[one.end] = upright
				? { x: at.x, y: at.y + shift }
				: { x: at.x + shift, y: at.y };

			if (pitch < row) one.line.crowded = true;
		});
	}
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
function Connections ({ box, joins, touched, cell, when, patching, onFlip, patchable }) {
	const [drawn, setDrawn] = useState([]);

	useLayoutEffect(() => {
		const wrap = box.current;

		if (!wrap || !joins.length) { setDrawn((was) => (was.length ? [] : was)); return; }

		const measure = () => {
			const outer = wrap.getBoundingClientRect();

			/* Relative to the scrolled content rather than to the viewport,
			   because that is the space the blocks themselves are placed in. A
			   line has to stay on its block when the page scrolls. */
			const placed = (element) => {
				const at = element.getBoundingClientRect();

				return {
					x: at.left - outer.left + wrap.scrollLeft,
					y: at.top - outer.top + wrap.scrollTop,
					w: at.width, h: at.height,
				};
			};

			const where = new Map();

			for (const part of wrap.querySelectorAll("[data-part]")) {
				where.set(part.dataset.part, placed(part));
			}

			/* How high up a block one of its rows is drawn, asked of the page
			   rather than worked out: a row's height depends on the cell size, on
			   whether the pattern is windowed and on how far that window has
			   been scrolled, and the rendering is the only thing that knows all
			   three. */
			const levelOf = (part, row) => {
				const label = wrap.querySelector(
					`[data-part="${CSS.escape(part)}"] [data-row="${CSS.escape(row)}"]`);

				if (!label) return null;

				const at = placed(label);

				return at.y + at.h / 2;
			};

			const inset = marked(cell, ANCHOR.floor, ANCHOR.share, ANCHOR.ceiling);
			const laid = [];

			for (const join of joins) {
				const from = where.get(join.from);
				const to = where.get(join.to);

				if (!from || !to) continue;

				const level = join.row ? levelOf(join.to, join.row) : null;
				const found = anchorsFor(
					from, to, level, inset, join.slot || 0, join.slots || 1);

				laid.push({ ...join, ...found, boxes: { from, to } });
			}

			/* In two passes, because where one cable's end goes depends on how
			   many others reached the same edge — which is not known until they
			   have all been placed once. */
			fanTerminals(laid, inset, controlRow(cell));

			const next = laid.map(({ boxes, ends, ...line }) => line);

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

	const jack = marked(cell, JACK.floor, JACK.share, JACK.ceiling);

	/* What a fitting is worth when it can be taken hold of: half a control row,
	   so the whole disc is a row across (#2107). A lug is `jack` and stays a
	   mark, because a hard-wired line cannot be moved. */
	const grip = controlRow(cell) / 2;

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
		${/* Room for whatever reaches past the two points measured above: a
		     cable's sag hangs below the lower of its two ends, and a jack is
		     centred on an endpoint and so spills by its own radius. */ ""}
		<svg class="joins"
			width=${Math.ceil(Math.max(extent.x, patching ? patching.at.x : 0) + jack) + 1}
			height=${Math.ceil(
				Math.max(extent.y, patching ? patching.at.y : 0) + jack + SAG_CEILING) + 1}>
			${/* The cable in the air, drawn from the outlet it was taken from to
			     wherever the finger is. Not a join yet — nothing has been asked
			     of the app — so it carries the ring's colour, which is what this
			     surface uses for a request that has not landed (#2046). */ ""}
			${patching && (() => {
				const span = Math.hypot(patching.at.x - patching.a.x, patching.at.y - patching.a.y);
				const dip = Math.min(SAG_CEILING, Math.max(SAG_FLOOR, span * SAG_SHARE));
				const reach = (patching.at.x - patching.a.x) * 0.25;

				return html`
					<g class="join loose">
						<path class="cable" d=${`M ${patching.a.x} ${patching.a.y}`
							+ ` C ${patching.a.x + reach} ${patching.a.y + dip}`
							+ ` ${patching.at.x - reach} ${patching.at.y + dip}`
							+ ` ${patching.at.x} ${patching.at.y}`} />
						<circle class="collar" cx=${patching.a.x} cy=${patching.a.y} r=${jack} />
						<circle class="plug" cx=${patching.a.x} cy=${patching.a.y} r=${jack * 0.46} />
						<circle class="plug" cx=${patching.at.x} cy=${patching.at.y}
							r=${jack * 0.46} />
					</g>`;
			})()}
			${drawn.map((line) => {
				/* **A cable, because that is what this is.** A person who
				   patches a modular, a mixer or a stage box already knows that
				   a lead runs from a socket to a socket and hangs a little in
				   between — and that reading is worth more than the arrowhead
				   it replaces, which was a triangle floating in the middle of a
				   straight line with nothing physical about it.
				
				   The sag is not decoration either: it is what makes two
				   crossing cables readable as two cables, which is the whole
				   reason a real patchbay is legible at all. */
				const span = Math.hypot(line.b.x - line.a.x, line.b.y - line.a.y);
				const dip = Math.min(SAG_CEILING, Math.max(SAG_FLOOR, span * SAG_SHARE));
				const reach = (line.b.x - line.a.x) * 0.25;

				const c1 = { x: line.a.x + reach, y: line.a.y + dip };
				const c2 = { x: line.b.x - reach, y: line.b.y + dip };

				/* **A loom does not hang.** A hard-wired line is taut and
				   half the weight, so the two kinds are told apart at a glance
				   rather than by comparison — which is the whole point of
				   drawing them differently at all. */
				const cable = line.wired
					? `M ${line.a.x} ${line.a.y} L ${line.b.x} ${line.b.y}`
					: `M ${line.a.x} ${line.a.y}`
						+ ` C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${line.b.x} ${line.b.y}`;

				/* Where the switch rides. The midpoint of a cubic is
				   (A + 3C₁ + 3C₂ + B) / 8, which for these control points is
				   the straight midpoint pulled down by three quarters of the
				   sag — so the switch sits on the cable rather than beside it. */
				const middle = {
					x: (line.a.x + line.b.x) / 2,
					y: (line.a.y + line.b.y) / 2 + (line.wired ? 0 : dip * 0.75),
				};

				/* **Three row-sized targets need a cable long enough to hold
				   them.** Two blocks side by side make a lead forty pixels
				   long, and the switch and both fittings landed on the same
				   spot — measured on the rig, not guessed at. #2107 settles it:
				   a thing that cannot be given a row across must not be
				   touchable. The switch stays, because silencing a route is the
				   commoner act and it was there first; the fittings go back to
				   being marks until there is room, and shrink visibly, so the
				   change is something seen rather than discovered by pressing. */
				const holdable = !line.wired && !line.crowded
					&& span >= controlRow(cell) * 3.2;
				const fitting = holdable ? grip : jack;

				const live = touched === line.from || touched === line.to;
				const flip = line.control && onFlip
					? (event) => { event.preventDefault(); onFlip(line); }
					: null;

				return html`
					<g key=${`${line.from}>${line.to}/${line.layer || ""}`}
						class=${`join ${line.wired ? "wired" : "patched"} `
							+ `${holdable ? "holdable " : ""}`
							+ `${live ? "live" : ""} ${line.off ? "off" : ""}`
							+ `${flip ? " switchable" : ""}`}
						data-join=${`${line.from}>${line.to}`}>
						<path class="cable" d=${cable} />
						${line.wired
							? html`
								${/* **Lugs, not fittings.** A wired line is
								     terminated rather than plugged, so its ends
								     are square where a patch cable's are round —
								     shape carrying the difference, as it does
								     for a routed note against an invented one. */ ""}
								<rect class="lug" x=${line.a.x - jack * 0.42}
									y=${line.a.y - jack * 0.42}
									width=${jack * 0.84} height=${jack * 0.84} />
								<rect class="lug" x=${line.b.x - jack * 0.42}
									y=${line.b.y - jack * 0.42}
									width=${jack * 0.84} height=${jack * 0.84} />`
							: html`
								${/* **The ends say which way it runs**, which is
								     what the arrowhead was for and what a cable
								     does not say by itself. The source end is a
								     plug — solid, seated in a collar — and the
								     destination is a socket, open. Something
								     plugged *into* something reads as a
								     direction without a symbol to learn. */ ""}
								${/* **A fitting you can take hold of is a target,
								     so it is a row across** — #2107, and the
								     reason a wired line's lugs stay small is
								     that they are marks and cannot be moved.
								     Size follows touchability, which is the
								     rule saying the same thing from the other
								     side. */ ""}
								<circle class="collar" cx=${line.a.x} cy=${line.a.y}
									r=${fitting}
									onPointerDown=${holdable
										? (event) => patchable.onTake(line, "plug", event) : null}
									onPointerMove=${holdable ? patchable.onMove : null}
									onPointerUp=${holdable ? patchable.onEnd : null}
									onPointerCancel=${holdable ? patchable.onEnd : null} />
								<circle class="plug" cx=${line.a.x} cy=${line.a.y}
									r=${fitting * 0.4} />
								<circle class="socket" cx=${line.b.x} cy=${line.b.y}
									r=${fitting}
									onPointerDown=${holdable
										? (event) => patchable.onTake(line, "socket", event) : null}
									onPointerMove=${holdable ? patchable.onMove : null}
									onPointerUp=${holdable ? patchable.onEnd : null}
									onPointerCancel=${holdable ? patchable.onEnd : null} />
								<circle class="hole" cx=${line.b.x} cy=${line.b.y}
									r=${fitting * 0.3} />`}
						${/* The switch, and it looks like one: a disc riding on the
						     cable. Filled while the link is sounding, hollow when it
						     is not — the same sentence every other toggle on this
						     surface says, in the shape a line can carry.
						
						     Drawn only where there is something to switch, so the
						     disc means "this is a control" and its absence means
						     "this is a mark". A generator's line is a mark: its
						     switch lives in its own block (#2107). */ ""}
						${flip && html`
							<circle
								class="node" cx=${middle.x} cy=${middle.y}
								r=${controlRow(cell) / 2}
								onPointerDown=${flip} />`}
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

				/* Shown only once it has somewhere to be. Until the first beat
				   arrives there is no anchor, so nothing above runs and the bar
				   kept its CSS position — parked against the block's left edge,
				   two pixels wide and full height, which the gaps between rows
				   chopped into a column of little marks down the side of every
				   pattern. Simon saw them twice and read them as leftovers,
				   which is exactly what they were. */
				bar.current.hidden = false;
			}

			frame = requestAnimationFrame(move);
		};

		move();
		return () => cancelAnimationFrame(frame);
	}, [steps, beats]);

	return html`<div class="playhead" hidden ref=${bar}></div>`;
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
function Transport ({ control, name, fields, up, anchor, onSet }) {
	const paused = fields.paused === true;
	const bpm = fields.bpm;
	/* **No invented bounds.** This read `|| [40, 240]`, and `nudge` clamps to
	   whatever it finds — so an app declaring no range could not be taken
	   outside 40 to 240 BPM from the glass, with nothing on the panel saying
	   why or that a limit existed at all. 40 to 240 is a fact about the kind of
	   music this rig plays, which is exactly the sort of thing #2049 says must
	   not be written down here. An app that has bounds declares them and they
	   are honoured; one that does not gets no clamp, and refuses what it cannot
	   do with a reason the panel can show. */
	const [low, high] = control.tempo_range || [];
	const canPause = (control.fields || []).includes("paused");

	const nudge = (by) => {
		if (typeof bpm !== "number") return;

		const wanted = Math.round((bpm + by) * 10) / 10;

		onSet(`${name}/bpm`, Math.min(
			high === undefined ? wanted : high,
			Math.max(low === undefined ? wanted : low, wanted)));
	};

	/* **The counter is the largest thing here**, because on every machine these
	 * users own it is: an 808, an MPC, a tape remote, Logic's bar. Ours had a
	 * big word reading PAUSE and no position at all, which is the arrangement
	 * the other way round.
	 *
	 * `bar · beat · step`, which is Ableton's `bar.beat.sixteenth` said in the
	 * units this pattern actually has. **Elapsed time is deliberately absent**:
	 * it needs a position in seconds the transport does not declare, and a
	 * panel counting locally instead is wrong after the first pause or tempo
	 * change. Simon chose to leave the neighbour alone, so the counter says
	 * only what can be known. A stop key is absent for the same reason — the app
	 * declares no stop, and the rule since #2046 is to lose a control rather
	 * than draw a broken one. */
	const [reading, setReading] = useState(null);
	const from = useRef(anchor);

	useEffect(() => { from.current = anchor; }, [anchor]);

	useEffect(() => {
		let frame;

		const tick = () => {
			const held = from.current;

			if (held && held.interval && held.beats) {
				const perBar = Math.max(1, held.beats);
				const perBeat = Math.max(1, Math.round((held.steps || perBar) / perBar));

				/* Held where it stopped while the clock is held: a paused
				   transport sends no beats, so extrapolating would run the
				   counter on with nothing to correct it. */
				const on = paused
					? held.beat
					: held.beat + Math.min((performance.now() - held.at) / 1000 / held.interval, 1);

				const bar = Math.floor(on / perBar) + 1;
				const beat = Math.floor(on % perBar) + 1;
				const step = Math.floor((on % 1) * perBeat) + 1;

				const said = `${String(bar).padStart(3, "0")}\u00b7${beat}\u00b7${step}`;

				setReading((was) => (was === said ? was : said));
			}

			frame = requestAnimationFrame(tick);
		};

		tick();

		return () => cancelAnimationFrame(frame);
	}, [paused]);

	return html`
		<div class="transport">
			${canPause && html`
				<div class="tkeys" role="group" aria-label="transport">
					<button
						class=${`tkey ${paused ? "" : "engaged"}`}
						disabled=${!up}
						aria-pressed=${paused ? "false" : "true"}
						title="play"
						onPointerDown=${(event) => {
							event.preventDefault();
							if (paused) onSet(`${name}/paused`, false);
						}}
					><${Icon} of="play" filled /></button>
					<button
						class=${`tkey ${paused ? "engaged" : ""}`}
						disabled=${!up}
						aria-pressed=${paused ? "true" : "false"}
						title="pause — the clock is held, not stopped"
						onPointerDown=${(event) => {
							event.preventDefault();
							if (!paused) onSet(`${name}/paused`, true);
						}}
					><${Icon} of="pause" filled /></button>
				</div>`}

			<div class="lcd count">
				<span class="lcd-value">${reading || "\u2014"}</span>
				<span class="lcd-label">bar · beat · step</span>
			</div>

			<div class="lcd">
				<span class="lcd-value">
					${typeof bpm === "number" ? bpm.toFixed(bpm % 1 ? 1 : 0) : "\u2014"}</span>
				<span class="lcd-label">tempo · bpm</span>
			</div>

			<div class="tempo">
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(-5); }}>−5</button>
				<button disabled=${!up} onPointerDown=${(e) => { e.preventDefault(); nudge(-1); }}>−1</button>
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
/* How the panel's own network is doing, in the place the other diagnostics
 * already are.
 *
 * **Typical and worst, because only the second answers the question.** The
 * abandon timer exists for a request that never comes back, and choosing its
 * length means knowing how slow a request can be while still being fine. A
 * median alone would say four milliseconds and settle nothing; three reviews
 * have now deferred that number for want of this one.
 *
 * Drawn only once there is something to say, so a panel that has just opened
 * does not show a figure made from a single sample. */
function Trip ({ trips }) {
	if (!trips || trips.length < 8) return null;

	const sorted = [...trips].sort((one, two) => one - two);
	const middle = sorted[Math.floor(sorted.length / 2)];
	const worst = sorted[sorted.length - 1];

	return html`
		<span class="build trip"
			title="round trip to the service: typical and worst of the last two minutes"
		>${Math.round(middle)} / ${Math.round(worst)} ms</span>`;
}

function Build ({ service, stale }) {
	if (!service) return null;

	if (stale) {
		return html`
			<button class="reload" onPointerDown=${(event) => { event.preventDefault(); location.reload(); }}>
				newer page available — tap to load it
			</button>`;
	}

	/* **The case the build stamp cannot see** (#2164).
	 *
	 * A stale build means this browser is holding an old page, and reloading
	 * fixes it — that is the branch above. But the service serves the client
	 * from disk on *every* request, so a reload always gets the newest
	 * JavaScript, and the build hash therefore matches even when the running
	 * Python is hours older than the files it is serving. Everything looks
	 * picked up and nothing is: it cost a round trip on 2026-09-05, where a
	 * feature was declared broken on the glass with both processes predating it.
	 *
	 * That case has exactly one symptom available, and it is this one: the page
	 * and the service disagree about the contract while agreeing about the
	 * build. So the message says *restart the service*, which is the fix, rather
	 * than "reload", which is the fix for the other one and does nothing here. */
	const gap = contractGap(service.contract);

	if (gap) {
		/* **A major difference does not say which side is behind**, on purpose.
		   Within one major number this project's own numbering is additive, so
		   whichever end is behind is missing something rather than misreading
		   it, and naming the direction is the useful thing to say. Across one,
		   a frame either end already knows may have changed shape underneath
		   it — and then "which is behind" is the wrong question to answer
		   confidently on a bar. */
		const said = {
			older: "service is behind this page — restart it",
			newer: "this page is behind the service — reload it",
			major: "page and service disagree — restart the service",
			unreadable: "the service named no contract version",
		}[gap];

		return html`
			<span class=${gap === "older" || gap === "newer" ? "build mismatch" : "build mismatch grave"}
				title=${`this page speaks contract ${CONTRACT}; the service speaks ${service.contract}`}
			>${said}</span>`;
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
function autoPlace (blocks, across, frame) {
	const placed = {};

	let x = 0;
	let y = 0;
	let tallest = 0;

	for (const block of blocks) {
		/* A block's footprint in cells comes from what is in it: the label
		   column plus a cell per step across, a title plus a cell per row
		   down. Nothing measured, because nothing here needs pixels.
		
		   Plus the block's own frame, and then a cell of air on each side.
		   Blocks packed edge to edge read as one surface with lines drawn on it;
		   a lane between them says they are separate things, which they are. The
		   frame has to be counted or the lane is the lane minus the frame, which
		   is how a padding added for looks quietly ate a rule. A person who wants
		   them touching can drag them together, and this stops being consulted
		   for that block the moment they do. */
		const wide = LABEL_CELLS + block.steps + frame + SEPARATION;
		const high = 1 + block.rows + frame + SEPARATION;

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

/* How many cells a block's own frame takes, over and above what is inside it.
 *
 * At the tested size, deliberately, and for the same reason as the width above:
 * a starting arrangement worked out from the size in force would move every time
 * somebody changed that setting. */
function frameInCells () {
	const tested = SIZES.find((size) => size.key === "tested").px;

	return Math.ceil((PAD * 2) / (tested + GAP));
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

		if (Number.isFinite(pinched) && pinched >= ZOOM_FLOOR) { setCell(pinched); return; }

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

			const outer = box.getBoundingClientRect();
			const shape = getComputedStyle(box);

			const room = {
				width: outer.width - parseFloat(shape.paddingLeft) - parseFloat(shape.paddingRight) - FIT_SLACK,
				height: outer.height - parseFloat(shape.paddingTop) - parseFloat(shape.paddingBottom) - FIT_SLACK,
			};

			/* The size everything on the glass is drawn at right now, asked of
			   the stylesheet because that is what the measurements below are
			   measurements of. */
			const drawn = parseFloat(
				getComputedStyle(document.documentElement).getPropertyValue("--cell"));

			if (!Number.isFinite(drawn) || drawn <= 0) return;

			/* **The part of a block that does not scale — one block at a time.**
			 *
			 * It used to be measured from whichever part came first in the DOM
			 * and then applied to every block on the page, which is only right
			 * when they are all the same shape. A note grid carries a velocity
			 * lane, a settings strip and a footer; a params block has no footer
			 * at all. First block a note grid and everything else was
			 * over-measured, so the fit chose a smaller cell than it needed to;
			 * first block a params block and the note grid was under-measured
			 * and overflowed the box the fit was solving for. Silent both ways,
			 * and which way round depended on arrangement order — which a
			 * person changes by dragging.
			 *
			 * **Chrome is the residue**: what a block measures, less what the
			 * model already counts for it at the size it is drawn at. Defining
			 * it that way rather than as "everything but the grid and the
			 * title" also settles the note grid's double count — its lane and
			 * its settings strip are *already* in `block.rows` (`LANE_CELLS +
			 * NOTE_CONTROL_CELLS`), so subtracting the model's own arithmetic
			 * subtracts them exactly once. Whatever `blockSize` will add back,
			 * this took away. */
			const chromeOf = new Map();

			for (const part of box.querySelectorAll(".part[data-part]")) {
				const named = blocks.find((one) => one.name === part.dataset.part);

				if (!named) continue;

				const whole = part.getBoundingClientRect();
				const modelled = blockSize(named, drawn, { x: 0, y: 0 });

				chromeOf.set(named.name, {
					x: whole.width - modelled.width,
					y: whole.height - modelled.height,
				});
			}

			if (!chromeOf.size) return;

			/* A block on the page that has not been drawn yet has nothing of
			   its own to measure. The largest residue measured stands in for
			   it, because over-measuring costs a smaller cell and
			   under-measuring overflows the glass. */
			const spare = {
				x: Math.max(...[...chromeOf.values()].map((one) => one.x)),
				y: Math.max(...[...chromeOf.values()].map((one) => one.y)),
			};

			const fits = (candidate) => {
				const pitch = candidate + GAP;

				return blocks.every((block) => {
					const at = solving.current[block.name] || { x: 0, y: 0 };
					const size = blockSize(block, candidate, chromeOf.get(block.name) || spare);

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
			Math.min(FIT_CEILING, Math.max(ZOOM_FLOOR, gesture.from * ratio)));

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
/* Light, dark, or whatever the machine says.
 *
 * Simon asked for all three, and the third is the default: a theme is a property
 * of the glass and the room it is in, and the browser has already been told
 * which. What it cannot know is that this particular room has no ceiling lights
 * (#1959) — so the other two exist, and pinning one is one tap.
 *
 * Kept on the panel rather than anywhere shared, for the same reason the cell
 * size is (#2055): one panel wanting dark and another light is the ordinary
 * case, not a conflict to resolve. A page hung on a wall and a tablet carried
 * around the room are two different rooms.
 *
 * The attribute is also written by `index.html` before the first paint, so a
 * pinned theme does not flash the other one on the way in. This writes it again
 * on mount, which costs nothing and means the two cannot disagree. */
const THEME_KEY = "superintendent.theme";

/* **The name carries the reference without claiming it** (#2194). Each of the
   eight is drawn from a machine or a record, and which one is in #2190 and in
   the stylesheet's own comment beside the values — never here, because this
   string is a product string and the key below is written into `localStorage`.

   `key` is the `data-theme` attribute, so it is also the CSS selector: adding a
   theme is a block in `style.css` and a line here, and a test asserts the two
   lists are the same. */
const THEMES = [
	{ key: "system", label: "Match system", short: "system" },
	{ key: "light", label: "Light", short: "light" },
	{ key: "dark", label: "Dark", short: "dark" },
	{ key: "modular", label: "Modular", short: "modular" },
	{ key: "phosphor", label: "Phosphor", short: "phosphor" },
	{ key: "phaedra", label: "Phaedra", short: "phaedra" },
	{ key: "constructor", label: "Constructor", short: "constructor" },
	{ key: "aluminium", label: "Aluminium", short: "aluminium" },
	{ key: "airports", label: "Airports", short: "airports" },
	{ key: "oxygene", label: "Oxygène", short: "oxygène" },
	{ key: "workbench", label: "Workbench", short: "workbench" },
];

function rememberedTheme () {
	try {
		const held = localStorage.getItem(THEME_KEY);

		return THEMES.some((one) => one.key === held) ? held : "system";

	} catch (error) {
		/* Storage can be refused outright rather than merely be empty. A panel
		   in that state works; it just follows the machine every time. */
		return "system";
	}
}

function useTheme () {
	const [choice, setChoice] = useState(rememberedTheme);

	useEffect(() => {
		/* Nothing set is the third state rather than a missing one: it leaves
		   `color-scheme: light dark` in force, which is what makes the system's
		   answer the answer. */
		if (choice === "system") delete document.documentElement.dataset.theme;
		else document.documentElement.dataset.theme = choice;

		try {
			localStorage.setItem(THEME_KEY, choice);
		} catch (error) {
			/* As above: forgetting between reloads is the only consequence. */
		}
	}, [choice]);

	return { choice, choose: setChoice };
}

function Theme ({ choice, onChoose }) {
	const [open, setOpen] = useState(false);
	const named = THEMES.find((one) => one.key === choice) || THEMES[0];

	return html`
		<div class="theme">
			<button
				class=${open ? "open" : ""}
				onPointerDown=${(event) => { event.preventDefault(); setOpen(!open); }}
			>theme · ${named.short}</button>

			${open && html`
				<div role="group" class="choices">
					${THEMES.map((theme) => html`
						<button
							key=${theme.key}
							class=${`choice ${theme.key === choice ? "chosen" : ""}`}
							onPointerDown=${(event) => {
								event.preventDefault();
								onChoose(theme.key);
								setOpen(false);
							}}
						>
							${/* The swatch is the theme rather than a copy of it: the
							     element carries that theme's own `data-theme`, so the
							     stylesheet's block for it applies here and the swatch
							     paints in whatever that block says. No palette value is
							     written twice. */ ""}
							<i data-theme=${theme.key}></i>
							<span>${theme.label}</span>
						</button>`)}
				</div>`}
		</div>`;
}

function Sizes ({ cell, choice, onChoose }) {
	const [open, setOpen] = useState(false);

	return html`
		<div class="sizes">
			<button
				class=${open ? "open" : ""}
				onPointerDown=${(event) => { event.preventDefault(); setOpen(!open); }}
			>size · ${cell}px</button>

			${open && html`
				<div role="group" class="choices">
					${SIZES.map((size) => html`
						<button
							key=${size.key}
							class=${`choice ${size.key === choice ? "chosen" : ""}`}
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

	/* Every recent round trip to the service, so the panel can say what its own
	   network is doing. Read from the pong the link already sends. */
	const [trips, setTrips] = useState([]);
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
	const [sending, setSending] = useState(null);
	const [moved, setMoved] = useState({});
	const [touched, setTouched] = useState(null);
	const [realised, setRealised] = useState({});

	const theme = useTheme();

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
						} else if (rest.length === 1 && rest[0] === "rows"
							&& declared && GRID_KINDS.includes(declared.type)) {
							/* **The whole grid at once**, which is how a clear
							   travels and how a pattern could later be pasted
							   in. `rows` is a pseudo-key: it does not name
							   something *in* the grid's state, it names all of
							   it — so unlike every other length-one path this
							   one replaces rather than writes a field.

							   Without this branch it fell through below and
							   wrote a row literally called `rows` beside the
							   real ones, leaving every step lit on the glass
							   while the app had actually emptied the pattern.
							   Silent, and the wrong way round: the panel
							   showing notes that make no sound is this
							   project's own cardinal defect.

							   The mute lives beside the rows and is a path of
							   its own, so it survives the replacement — the
							   same reasoning `_apply_cell` follows on the
							   service, and it has to be the same in both or a
							   panel that reloads disagrees with one that did
							   not. */
							const held = app[control] || {};

							app[control] = "enabled" in held
								? { ...frame.v, enabled: held.enabled }
								: { ...frame.v };
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

					/* **A dot means "an algorithm put this here *this cycle*",
					 * and a held clock has no cycle.**
					 *
					 * Simon: the Euclidean feeding the kick is off and its dots
					 * are still on the grid, never changing. They were, because
					 * `realised` is an event sent once a cycle (#1965) and the
					 * transport was paused — so the last set the panel received
					 * stayed on the glass, outliving the thing that put it
					 * there and then outliving the generator itself.
					 *
					 * Cleared when the clock is held, and again whenever a stack
					 * changes: bypassing a generator makes every dot it
					 * contributed a statement about a cycle that will not
					 * happen. Both heal themselves on the next cycle, which is
					 * exactly what a thing nothing stores should do. */
					if (frame.path.endsWith("/paused") && frame.v === true) {
						setRealised({});
					}

					if (frame.path.endsWith("/layers")) {
						setRealised({});
					}

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
					setService({
						version: frame.version, build: frame.build,
						/* Read at last (#2164). It has been arriving since 1.1.0
						   and going straight in the bin. */
						contract: frame.contract,
					});
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
						setAnchor({
							beat: frame.beat, at: performance.now(), interval: frame.interval,
							/* Carried so the counter can say which bar and which
							   step of it, which is arithmetic on what the app
							   already declares rather than a fifth number that
							   could disagree with the other four. */
							steps: frame.steps, beats: frame.beats,
						});
					}

					/* What the algorithms put on a pattern this cycle. Held apart
					   from every control's state and never merged into it: these
					   notes are not intent and nothing keeps them (#1965). A
					   person's taps stay the only thing anything stores. */
					if (frame.name === "realised" && typeof frame.control === "string") {
						setRealised((was) => ({ ...was, [frame.control]: frame.cells || {} }));
					}
					break;
			}
		};

		link.current = new Link(onFrame, setStatus, setTrips);

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
		 * always the truth — is all that is left.
		 *
		 * **The one it replaces is cleared first.** Overwriting the map entry
		 * left the earlier timer running and unreachable, and every frame of a
		 * dial drag, a range drag, a velocity drag and every path in the
		 * reconnect re-send loop sends two on one path before the first is
		 * answered. Five seconds later the orphan fires: it flashes a control
		 * whose request succeeded as refused, and — worse, because it is not
		 * merely cosmetic — it drops the ring of whatever request is in flight
		 * on that path at the time. */
		clearTimeout(expiries.current.get(path));

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
	const routes = [];

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
			const voices = (feeds && controls[feeds].rows) || [];

			/* Which row of the pattern this contribution acts on, if it acts on
			   one — so its line can arrive level with that row rather than at the
			   middle of a pattern with ten of them (Simon, 2026-09-05).
			 *
			 * **Told, not guessed.** The app says a parameter is a pitch and the
			 * composition says which pitches exist; the join between them is
			 * declared as `role: "pitch"`, and this reads that word. My first
			 * version inferred it from the option list — a choice offering
			 * exactly this pattern's rows — and it was wrong for an ordinary
			 * case: a composition may offer a generator a wider pool of voices
			 * than any one pattern has rows, and then the inference finds
			 * nothing. The knowledge existed upstream and was being thrown away.
			 *
			 * The row still has to be a row of *this* pattern. A pool may hold
			 * voices this grid does not draw, and pointing at one of those would
			 * be pointing at nothing.
			 *
			 * A generator that names no row feeds the whole pattern, and its line
			 * says so by pointing at the pattern rather than at a part of it. */
			const voiceOf = (generator, layer) => {
				for (const field of (generator ? generator.parameters : [])) {
					if (field.role !== "pitch") continue;

					const chosen = (layer.params || {})[field.name];

					if (typeof chosen === "string" && voices.includes(chosen)) return chosen;
				}

				return null;
			};

			for (const layer of held) {
				/* **A route is a line, and nothing else.**
				
				   It had a window of its own, carrying its bypass, its place in
				   the stack and a picker for where it came from. Simon: "surely
				   a *route* is a line with an arrow head?" He is right, and the
				   window was answering a question nobody asked — a connection is
				   not a thing that sits somewhere, it is the fact that two
				   things are joined. Its one real control moved to the head of
				   its own arrow, which is where a hand goes to find it. */
				if (layer.kind === "pattern") {
					if (gridNames.includes(layer.source) && feeds) {
						routes.push({
							from: layer.source, to: feeds, row: null,
							control: name, layer: layer.id, off: Boolean(layer.bypassed),

							/* Patched, not wired: a grid exists on its own,
							   carries the same notes wherever it goes, and can
							   be plugged into as many patterns as you like. */
							wired: false,
						});
					}

					continue;
				}

				const generator = offered.find((one) => one.name === layer.generator);

				contributions.push({
					key: `${name}/${layer.id}`,
					control: name, layer, layers: held, offered: generator, feeds,
					voice: voiceOf(generator, layer),

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
			               about: controls[name].about || [],
			               rows: Math.max(1, (controls[name].fields || []).length),
			               steps: PARAM_CELLS });
			continue;
		}

		/* A pitched pattern is as tall as its rows plus the velocity lane
		   beneath them, which is what the fit has to solve for rather than the
		   rows alone. Every pattern carries a footer, because every pattern can
		   be cleared. */
		/* Which stacks would take this grid's notes, so a person holding a grid
		   can send it somewhere rather than having to go to the thing that
		   receives it and ask for it by name.
		
		   Simon asked "how should I connect the output of shared-drums to an
		   instrument?", and the honest answer was: from the other end. That is
		   backwards from how anybody thinks about a signal — you have a thing,
		   and you send it. The receiving end still works and still reads well
		   for "what is this pattern made of"; this is the same fact asked from
		   the side a person is standing on. */
		const sends = Object.keys(controls).filter(
			(one) => kindOf(one) === "recipe" && (controls[one].sources || []).includes(name));

		windows.push({
			key: name, control: name, title: named(name),
			about: controls[name].about || [],
			add: stackFor(name) || null, clear: true,
			sends: sends.length ? sends : null,

			/* Absent means on. A control the app has said nothing about is
			   playing, which is what every grid did before there was a switch. */
			live: ((state[appName] || {})[name] || {}).enabled !== false,
			rows: Math.min(controls[name].rows.length, controls[name].visible_rows || Infinity)
				+ (kindOf(name) === "note_grid" ? NOTE_CONTROL_CELLS : 0)
				+ (kindOf(name) === "note_grid" && Array.isArray(controls[name].velocity_range)
					? LANE_CELLS : 0) + 1,
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
	/* Every line on this page, and which way each one runs.
	 *
	 * A generator has one: itself into the pattern it builds. A routed grid has
	 * two — the grid it takes from into it, and it into the pattern it builds —
	 * because it is a contribution *and* a thing that is contributed to. That is
	 * the first block here to have both, and it is what makes the question of
	 * how to tell an in from an out a question about something real (#2108). */
	const joins = [
		...routes,
		...contributions
			.filter((one) => one.feeds)
			.map((one) => ({
				from: one.key, to: one.feeds, row: one.voice,
				off: Boolean(one.layer.bypassed),

				/* **Hard-wired, and drawn so.** Simon settled the metaphor: a
				   generator is created from a pattern, belongs to it and dies
				   with it, so there is no cable and nothing to unplug. Drawing
				   it as a patch cable promised a gesture the model cannot
				   offer, and "why can't I drag this?" now answers itself —
				   because it is not patched, it is wired in. */
				wired: true,

				/* No switch on this line, and that is the correction Simon made.
				
				   A generator is a stack entry in exactly one pattern, so it has
				   exactly one link and its own on/off *is* that link's — one
				   stored value. I showed it in two places and called it a
				   feature. It is not: a person reading two switches reasonably
				   believes they say two things, and he asked the question that
				   proves it — what if the source feeds several destinations?
				
				   The rule that falls out is the same shape as the size rule:
				   **a switch lives with the thing it switches.** A generator has
				   a block, so its switch is in its block and its arrowhead is a
				   mark. A route has only a line, so its switch is on the line.
				   Nothing has two, and nothing switchable has none. */
			})),
	];

	/* Which lug on a voice each wired line takes, and how many there are.
	 *
	 * Counted after the list is built, because a lug's place depends on its
	 * neighbours: with one generator on a voice it sits at the block's edge,
	 * and with three they queue outward from it. Order is the order they are
	 * built in, so the leftmost lug is the first to run. */
	const lugs = new Map();

	for (const join of joins) {
		if (!join.wired) continue;

		const lane = `${join.to}/${join.row}`;

		join.slot = lugs.get(lane) || 0;
		lugs.set(lane, join.slot + 1);
	}

	for (const join of joins) {
		if (join.wired) join.slots = lugs.get(`${join.to}/${join.row}`) || 1;
	}

	/* The switch on a line, for the links that have one.
	 *
	 * A route only — see above. The line still goes dashed when a generator is
	 * bypassed, because that is worth seeing from across the page; it just is
	 * not where you change it. */
	const flip = useCallback((join) => {
		const held = ((state[appName] || {})[join.control] || {}).layers || [];

		request(`${join.control}/layers`, held.map((layer) =>
			layer.id === join.layer ? { ...layer, bypassed: !layer.bypassed } : layer));
	}, [state, appName, request]);

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
		() => autoPlace(blocks, acrossAtTestedSize(), frameInCells()),
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

	/* What kind of thing each layer of a grid's stack is, by its id. */
	const layerKinds = (control) => {
		const stack = stackFor(control);
		const layers = stack ? ((state[appName] || {})[stack] || {}).layers || [] : [];

		return Object.fromEntries(
			layers.map((layer) => [layer.id, layer.kind === "pattern" ? "pattern" : "generator"]));
	};

	/* An id has to survive a round trip and be unique among its neighbours. The
	   clock alone is not enough: two taps inside a millisecond are a stutter
	   rather than an impossibility on a surface meant to be played. */
	const freshId = () => `l${Date.now().toString(36)}`
		+ `${Math.floor(Math.random() * 46656).toString(36)}`;

	const addLayer = (stack, layer) => {
		const held = ((state[appName] || {})[stack] || {}).layers || [];

		request(`${stack}/layers`, [...held, { id: freshId(), ...layer }]);
	};

	/* --- Patching one block into another by dragging a cable ---------------
	 *
	 * Simon: "add a contribution is not an intuitive way to connect items ... I
	 * wonder whether we might simply drag a cable out from a designated output
	 * terminal to the input terminal of the target?"
	 *
	 * **The destination is the whole block, not a second small jack.** On glass
	 * a big target beats a precise one every time, and a person dragging a lead
	 * is looking at where it is going rather than at a fitting on it. So there
	 * is one new control — the outlet — and everything that can receive says so
	 * by lighting up while a cable is in the air.
	 *
	 * It replaces "send to…", which asked the same question as a list. What it
	 * does not replace is adding a *generator*: that is creating a thing, not
	 * connecting two that already exist, and no cable can be dragged from
	 * something that is not on the glass yet. */
	const patch = useRef(null);
	const [patching, setPatching] = useState(null);

	/* **What the end in your hand could land on**, which is not the same set at
	   both ends of a cable.
	
	   Dragging the socket, you are choosing a destination, and a destination is
	   a block whose stack will take what is already plugged in at the far end —
	   that is `data-takes`, and it was the only set the page ever lit. Dragging
	   the plug, you are choosing a *source*, so the blocks that could answer are
	   the ones the destination's stack declares it takes from. Lighting
	   `data-takes` for that gesture showed precisely the blocks that cannot be
	   what you are looking for. The drop always resolved correctly; only the
	   affordance lied. */
	const offering = patching && patching.end === "plug" && patching.into
		? (controls[patching.into] || {}).sources || []
		: null;

	const wrapPoint = (event) => {
		const wrap = size.wrap.current;

		if (!wrap) return { x: 0, y: 0 };

		const outer = wrap.getBoundingClientRect();

		return {
			x: event.clientX - outer.left + wrap.scrollLeft,
			y: event.clientY - outer.top + wrap.scrollTop,
		};
	};

	const beginPatch = (from, event) => {
		event.preventDefault();
		event.currentTarget.setPointerCapture(event.pointerId);

		const at = wrapPoint(event);

		patch.current = { from, pointer: event.pointerId };
		setPatching({ from, a: at, at });
	};

	/* **Taking hold of a cable that is already patched.**
	 *
	 * Simon: "I might move a cable between targets — re-route my generator from
	 * one part to another ... I must be able to select an individual patch point
	 * to disconnect or move it."
	 *
	 * Either end comes away. The one still plugged in stays where it is and the
	 * other follows the finger, which is what happens when you pull a lead out
	 * of a rack — and letting go over nothing leaves it unpatched, because that
	 * is also what happens.
	 *
	 * The layer it came from is remembered and taken away on the release, so a
	 * cable moved is one route rather than two: the old one never survives to
	 * be silently doubled. */
	const beginRepatch = (line, end, event) => {
		event.preventDefault();
		event.currentTarget.setPointerCapture(event.pointerId);

		const at = wrapPoint(event);
		const held = { pointer: event.pointerId, was: { control: line.control, layer: line.layer } };

		if (end === "socket") {
			/* The source stays plugged in; the destination is in the hand. */
			patch.current = { ...held, from: line.from, end };
			setPatching({ from: line.from, a: line.a, at, end });
			return;
		}

		/* The destination stays; what feeds it is being chosen again. */
		patch.current = { ...held, into: line.control, end };
		setPatching({ from: null, a: line.b, at, end, into: line.control });
	};

	const movePatch = (event) => {
		if (!patch.current || patch.current.pointer !== event.pointerId) return;

		const at = wrapPoint(event);

		setPatching((held) => (held ? { ...held, at } : held));
	};

	const endPatch = (event) => {
		const held = patch.current;

		if (!held || held.pointer !== event.pointerId) return;

		patch.current = null;
		setPatching(null);

		const under = document.elementFromPoint(event.clientX, event.clientY);

		/* Where the finger let go. The fitting has the pointer captured, so
		   every event arrives here and the only way to know what was landed on
		   is to ask the document. */
		const landed = held.end === "plug"
			? (() => {
				const block = under && under.closest("[data-part]");
				const source = block && block.getAttribute("data-part");

				/* Choosing what feeds a pattern again: whatever is under the
				   finger has to be something that pattern's stack takes from. */
				return source && (controls[held.into].sources || []).includes(source)
					? { stack: held.into, source }
					: null;
			})()
			: (() => {
				const block = under && under.closest("[data-takes]");
				const stack = block && block.getAttribute("data-takes");

				/* Refused rather than sent: a stack says which sources it will
				   take, and a cable dropped somewhere that cannot hold it
				   should come away in the hand rather than produce a `nack` a
				   moment later. */
				return stack && (controls[stack].sources || []).includes(held.from)
					? { stack, source: held.from }
					: null;
			})();

		/* **One request, not two.** Taking the old route away and making the
		   new one were separate asks, and the second read the layers back
		   before the first had been confirmed — so putting a cable into the
		   socket it came out of left two routes where there should be one.
		   Computed together and sent once, a move is a move. */
		if (held.was && landed && landed.stack === held.was.control) {
			const layers = ((state[appName] || {})[held.was.control] || {}).layers || [];

			request(`${held.was.control}/layers`, [
				...layers.filter((layer) => layer.id !== held.was.layer),
				{ id: freshId(), kind: "pattern", source: landed.source },
			]);

			return;
		}

		/* Different stacks, or nowhere at all: the old route goes whatever
		   happens, because a cable pulled out and let go is unpatched. */
		if (held.was) {
			const layers = ((state[appName] || {})[held.was.control] || {}).layers || [];

			request(`${held.was.control}/layers`,
				layers.filter((layer) => layer.id !== held.was.layer));
		}

		if (landed) addLayer(landed.stack, { kind: "pattern", source: landed.source });
	};

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
				<${Theme} choice=${theme.choice} onChoose=${theme.choose} />
				<span class=${`lamp ${status === "up" ? "up" : ""}`}>${status === "up" ? "connected" : "offline"}</span>
				<${Build} service=${service} stale=${stale} />
			<${Trip} trips=${trips} />
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
					fields=${transportFields} up=${up} anchor=${anchor} onSet=${request} />`}
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
			<${Theme} choice=${theme.choice} onChoose=${theme.choose} />
			<span class=${`lamp ${status === "up" && up ? "up" : ""}`}>
				${status !== "up" ? "no service" : up ? "connected" : "app gone"}
			</span>
			<${Build} service=${service} stale=${stale} />
			<${Trip} trips=${trips} />
		</div>
		<div
			class=${`grid-wrap ${up ? "" : "absent"} ${locked ? "" : "unlocked"} ${
				size.cell < OVERVIEW_AT ? "overview" : ""} ${patching ? "patching" : ""} ${
				offering ? "sourcing" : ""}`}
			ref=${size.wrap}
			...${pinch}
		>
			${drawn.map((one) => html`
				<${Part} key=${one.key} name=${one.key} title=${one.title} about=${one.about}
					flavour=${one.live === false ? "silent" : ""}
					at=${layout[one.key]} cell=${size.cell} depth=${stacked.indexOf(one.key)}
					locked=${locked}
					${/* Which stack a cable dropped on this block would go into.
					     The whole block is the target, not a fitting on it: on
					     glass a big one beats a precise one, and a person
					     dragging a lead is looking at where it is going. */ ""}
					takes=${one.add && (controls[one.add].sources || []).length
						? one.add : null}
					${/* And the mirror of it: what this block could be taken
					     *from*, while a plug is looking for a new source. */ ""}
					offers=${offering && offering.includes(one.control) ? one.control : null}
					onMove=${(who, x, y) => rearrange(who, { x, y })}
					onRaise=${(who) => rearrange(who, null)}
					onHold=${setDragging}
					onSettled=${keep}
					onTouch=${setTouched}
					onClose=${one.layer ? () => request(`${one.control}/layers`,
						one.layers.filter((held) => held.id !== one.layer.id)) : null}
					footer=${html`
						<${Footer}
							outlet=${one.sends ? {
								onStart: (event) => beginPatch(one.control, event),
								onMove: movePatch,
								onEnd: endPatch,
							} : null}
							onAdd=${one.add ? () => setAdding(one.add) : null}
							${/* **One thing, so one word.** It said "add source"
							     while it did two jobs — create a generator, and
							     route a grid — and Simon named it as the
							     unintuitive way to connect items. Routing is a
							     cable now, made from the grid being routed, so
							     this adds the only thing a pattern can be added
							     *to* with. */ ""}
							adds="add generator"
							onSend=${one.sends ? () => setSending(one.control) : null}
							onClear=${one.clear ? () => setClearing(one.control) : null}
							live=${one.live}
							onLive=${one.clear
								? (want) => request(`${one.control}/enabled`, want)
								: undefined} />`}>
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
							<${NoteBlock} name=${one.control} control=${controls[one.control]}
								notes=${(state[appName] || {})[one.control] || {}} cell=${size.cell}
								pending=${pending} failed=${failed} onSet=${request} />`
						: html`
							<${Grid} control=${one.control} rows=${controls[one.control].rows}
								steps=${controls[one.control].steps}
								beats=${controls[one.control].beats || 4}
								${/* What a realised cell's weight is measured
								     against, which is the app's to say and not
								     this panel's to assume. */ ""}
								weights=${controls[one.control].velocity_range}
								cells=${(state[appName] || {})[one.control] || {}}
								drawn=${up ? realised[one.control] : null}
								${/* Which layer is a route and which is a
								     generator, so a dot can say which put it
								     there. Read from the stack rather than sent
								     with the event: the panel already holds the
								     layers, and a second copy could disagree. */ ""}
								kinds=${layerKinds(one.control)}
								visible=${controls[one.control].visible_rows} cell=${size.cell}
								pending=${pending} failed=${failed} onTap=${request} />`}
					${up && one.clear && html`
						<${Playhead} anchor=${anchor} steps=${controls[one.control].steps}
							beats=${controls[one.control].beats || 4}
							paused=${transportFields.paused === true} />`}
				<//>`)}

			${/* Told what could have moved a line, because measuring is what this
			     does and nothing else in the page will tell it. */ ""}
			<${Connections} box=${size.wrap} joins=${joins} touched=${touched} cell=${size.cell}
				patching=${patching} onFlip=${flip}
				patchable=${{ onTake: beginRepatch, onMove: movePatch, onEnd: endPatch }}
				when=${`${size.cell}|${JSON.stringify(layout)}|${JSON.stringify(joins)}`} />
		</div>

		${adding && controls[adding] && (() => {
			const added = (layer) => {
				addLayer(adding, layer);
				setAdding(null);
			};

			return html`
				<${Sheet} title="add generator" onClose=${() => setAdding(null)}>

					${/* **A grid is not on this list any more.** It used to be,
					     on the argument that a pattern to take from and a
					     generator to add are the same kind of thing — and they
					     are not. A generator is created here and belongs to this
					     pattern, hard-wired to it. A grid exists on its own and
					     is *patched* in, from its own outlet or its own "send
					     to…". Offering it here as well was the second of two
					     ways to make one connection, which is the shape this
					     whole pass has been removing. */ ""}
					${(controls[adding].generators || []).map((generator) => html`
						<button
							key=${generator.name}
							class=${`offer option ${generator.partial ? "partial" : ""}`}
							disabled=${generator.partial}
							onPointerDown=${(event) => {
								event.preventDefault();
								added({ kind: "generator", generator: generator.name, params: {} });
							}}
						>
							<b>${generator.name}</b>
							<i>${generator.partial
								? "takes something this panel cannot draw yet"
								: generator.summary}</i>
						</button>`)}
				<//>`;
		})()}

		${sending && html`
			<${Sheet} title=${`send ${named(sending)} to`} onClose=${() => setSending(null)}>
				${Object.keys(controls)
					.filter((one) => kindOf(one) === "recipe"
						&& (controls[one].sources || []).includes(sending))
					.map((stack) => {
						const into = controls[stack].builds;
						const already = (((state[appName] || {})[stack] || {}).layers || [])
							.some((layer) => layer.kind === "pattern" && layer.source === sending);

						return html`
							<button
								key=${stack}
								class=${`offer option ${already ? "here" : ""}`}
								onPointerDown=${(event) => {
									event.preventDefault();

									const held = ((state[appName] || {})[stack] || {}).layers || [];

									/* The same list, with this route in it or out of
									   it. One place to make a connection and unmake
									   it, on the thing a person is holding — the head
									   of the arrow silences a route and this is what
									   takes it away. */
									request(`${stack}/layers`, already
										? held.filter((layer) => !(layer.kind === "pattern"
											&& layer.source === sending))
										: [...held, {
											id: `l${Date.now().toString(36)}`
												+ `${Math.floor(Math.random() * 46656).toString(36)}`,
											kind: "pattern",
											source: sending,
										}]);

									setSending(null);
								}}
							>
								<b>${into ? named(into) : named(stack)}</b>
								<i>${already
									? "goes here — tap to stop"
									: "every note drawn here, played there as well"}</i>
							</button>`;
					})}
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
 * both are the browser deciding a musician's gesture means something else.
 *
 * A right-click is neither. It is a deliberate act by somebody with a mouse, and
 * on a desk it is how a person copies what the panel is showing — which was not
 * possible at all until Simon went looking for it. So the suppression is for the
 * pointer it was written for, and the stylesheet makes the same division for
 * selection a few lines further on. */
const byFinger = !window.matchMedia("(pointer: fine)").matches;

document.addEventListener("contextmenu", (event) => {
	if (byFinger) event.preventDefault();
});
document.addEventListener("gesturestart", (event) => event.preventDefault());
