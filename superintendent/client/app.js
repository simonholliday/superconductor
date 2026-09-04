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

/* Which page this browser is actually running.
 *
 * The service stamps the build into the script's own URL, which is the only
 * place a module can read its own identity from without being told it. A page
 * served by something that does not stamp it has none, and then says nothing
 * rather than claiming to match (#2056). */
const pageBuild = new URL(import.meta.url).searchParams.get("v");

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
			this.send({ t: "hello", contract: "1.1.0", client: clientId, page: "grid", ver: {}, token: null });
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
			this.send({ t: "hello", contract: "1.1.0", client: clientId, page: "grid", ver: {}, token: null });
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
}

/* ------------------------------------------------------------------ */
/* The grid                                                            */
/* ------------------------------------------------------------------ */

function Grid ({ control, rows, steps, cells, pending, failed, onTap }) {
	/* A label column bounded by the viewport, then one column per step at
	   whatever size is set. The columns are that size exactly rather than at
	   least it: a person who asks for compact cells wants the space back for
	   something else, not the same grid stretched to fill the glass again. */
	const style = {
		gridTemplateColumns: `var(--label) repeat(${steps}, var(--cell))`,
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
							data-path=${`${row}/${step}`}
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

/* The cell size, as a person chose it or as their own viewport implies.
 *
 * Returns the element to measure, the size in pixels, the choice behind it and
 * a way to change that choice. The choice is remembered on the panel, which is
 * the closest thing to per-person storage that exists while page files are
 * still unsettled (#1948) — one browser profile is one panel is, in practice,
 * one pair of hands. */
function useCellSize (rows, steps) {
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

		/* Fitting. The grid is one label column and `steps` cells across, and
		   `rows` deep, so the largest cell that fits is whichever of the two
		   directions runs out first. A couple of pixels are left over on each
		   axis: an exact fit that rounds the wrong way raises a scrollbar,
		   which narrows the box, which would start the sum again. */
		const fit = () => {
			const box = wrap.current;

			if (!box || !rows || !steps) return;

			const label = box.querySelector(".row-label");
			const shape = getComputedStyle(box);
			const gap = parseFloat(getComputedStyle(document.documentElement)
				.getPropertyValue("--gap")) || 0;

			if (!label) return;

			const padX = parseFloat(shape.paddingLeft) + parseFloat(shape.paddingRight);
			const padY = parseFloat(shape.paddingTop) + parseFloat(shape.paddingBottom);

			/* The border box, not the content box. A scrollbar takes its width
			   out of the content box, so measuring that would make the sum's
			   answer depend on the answer: fit smaller, scrollbar goes, fit
			   larger, scrollbar returns. The border box does not move. */
			const outer = box.getBoundingClientRect();

			const across = outer.width - padX - FIT_SLACK
				- label.getBoundingClientRect().width - gap * steps;
			const down = outer.height - padY - FIT_SLACK - gap * (rows - 1);

			const size = Math.floor(Math.min(across / steps, down / rows));

			setCell(Math.max(FIT_FLOOR, Math.min(FIT_CEILING, size)));
		};

		fit();

		/* The viewport is the input, so anything that changes it — a rotation,
		   a window resize, a browser leaving kiosk mode — has to be an input
		   too, rather than something only a reload would pick up. */
		const watcher = new ResizeObserver(fit);

		if (wrap.current) watcher.observe(wrap.current);

		return () => watcher.disconnect();
	}, [choice, rows, steps]);

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

	const link = useRef(null);
	const expiries = useRef(new Map());
	const wanted = useRef(new Map());

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

					setState((was) => {
						const app = { ...(was[frame.app] || {}) };

						if (rest.length === 1) {
							app[control] = { ...(app[control] || {}), [rest[0]]: frame.v };
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
	const controlName = Object.keys(controls).find((name) => controls[name].type === "step_grid");
	const up = appName ? present[appName] !== false : false;

	/* Asked for before the page can return early, because a hook must be. The
	   grid it measures may not exist yet, and it copes: nothing is fitted until
	   there is something on the glass to fit. */
	const declared = controlName ? controls[controlName] : null;
	const size = useCellSize(declared ? declared.rows.length : 0, declared ? declared.steps : 0);

	/* Both halves have to be known before they can disagree: a page served
	   without a stamp, or a service too old to send one, is not evidence of
	   anything and must not raise a warning it cannot justify. */
	const stale = Boolean(service && service.build && pageBuild && service.build !== pageBuild);

	if (!controlName) {
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
			${notice && html`<span class="warn">${notice}</span>`}
			${!up && !notice && html`<span class="warn">not running — taps will be refused</span>`}
			<${Sizes} cell=${size.cell} choice=${size.choice} onChoose=${size.choose} />
			<span class=${`lamp ${status === "up" && up ? "up" : ""}`}>
				${status !== "up" ? "no service" : up ? "connected" : "app gone"}
			</span>
			<${Build} service=${service} stale=${stale} />
		</div>
		<div class=${`grid-wrap ${up ? "" : "absent"}`} ref=${size.wrap}>
			<${Grid} control=${controlName} rows=${control.rows} steps=${control.steps}
				cells=${cells} pending=${pending} failed=${failed} onTap=${request} />
			${up && html`<${Playhead} anchor=${anchor} steps=${control.steps} beats=${control.beats || 4}
				paused=${transportFields.paused === true} />`}
		</div>`;
}

render(html`<${Panel} />`, document.getElementById("panel"));

/* A long press must not offer a context menu, and a double tap must not zoom:
 * both are the browser deciding a musician's gesture means something else. */
document.addEventListener("contextmenu", (event) => event.preventDefault());
document.addEventListener("gesturestart", (event) => event.preventDefault());
