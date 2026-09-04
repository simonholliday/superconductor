# Superintendent — code review, 2026-09-04 (second pass)

The second review of the day, and the codebase has roughly tripled since the
first: three new control kinds, a lattice, arrange mode, page sets, a save path
to the composition, and forty-two browser tests that now run. The earlier report
is `review_2026-09-04.md`; its findings are not repeated here except where they
are still open, and its "Not Issues" have been honoured.

**Baseline.** 158 tests pass, none skipped, including all 42 page tests in
Firefox. `mypy superintendent` is clean across 9 source files. The suite is
therefore trustworthy as evidence for the first time in this project's life —
which changes what a review is for, and is why this one leans on measurement
rather than on reading.

**Assessment.** No defect here can lose a person's work or stop the music, and
the architecture has held up under a great deal of new weight: the service still
knows nothing about any instrument, the adapter still imports nothing from
Subsequence, and the three new control kinds cost the protocol two optional
fields between them. The two findings that matter are both in the layout, both
were invisible to reading and found by measuring, and both bite hardest at the
small cell sizes Simon actually prefers. Everything else is small.

---

## High

### 1. An instrument's settings overlap each other below 44 px

`superintendent/client/style.css` (`.grid.params .setting`), `superintendent/client/app.js` (`Params`)

A settings block lays its fields out on the grid's own track sizing —
`grid-auto-rows: var(--cell)` — while each control inside carries
`min-height: max(44px, var(--cell))`, so that a switch stays big enough to press
however small the grids beside it are set. Below 44 px those two disagree and
the control overflows its row.

**Measured**, at the compact setting with a two-field block: the first setting
occupies 107–151 px and the second 133–177 px. **They overlap by 18 px.** With
eight fields, as the Minitaur has, the block's last control sits well outside
the block.

The intent behind each half is right — a lattice block must measure a whole
number of cells (#2078), and a control must stay pressable (#2055) — and they
were written three commits apart without meeting. The fix is to let the row
track grow: `grid-auto-rows: minmax(var(--cell), max-content)` on a params grid,
and count a field as `ceil(44 / (cell + gap))` cells when computing the block's
footprint so the lattice still knows how tall it is.

Not caught by the page tests because both consistency tests compare a *cell* in
one grid against a cell in another, and a settings block has no cells.

---

## Medium

### 2. Dragging a block resizes the whole page under the finger

`superintendent/client/app.js:1028` — correctness against a decision

`useCellSize`'s effect lists `JSON.stringify(layout)` among its dependencies, so
every time a dragged block crosses a cell boundary the fit runs again. Under
*fit the glass* — the default — the arrangement's bounding box has just grown,
so the fit answers by shrinking every cell on the page.

**Measured**, dragging one block 600 px to the right: `--cell` went from 53 px
to 31 px mid-drag and settled at 28 px. Every block on the page halves in size
while the finger is still down, including the one being dragged.

This contradicts #2072, which Simon settled explicitly: the person decides the
size, and if the components no longer fit **the page scrolls** rather than
rearranging or resizing itself. A drag is precisely the moment that decision was
made for.

Recommend that the fit ignore the layout while arranging is latched, and settle
once on leaving it — which is also where the arrangement is saved (#2075), so
the two would happen together and for the same reason.

Secondary, and much smaller: each re-fit disconnects and re-creates a
`ResizeObserver` and runs a seven-step binary search over every block. That is
several times per drag rather than per frame, so it is not a performance
problem; it is mentioned only because it disappears with the same fix.

### 3. The panel can only ever talk to one application

`superintendent/client/app.js:1296`, `:1311` — latent

`request()` sends every set to `Object.keys(apps)[0]`, and the whole page is
drawn from that same first app. A second application dialling in would have its
controls ignored and, worse, a tap on a control it declared would be sent to the
wrong app under a path that app does not have — which the receiving app would
correctly refuse, leaving a control that never moves.

Unreachable today because only Subsequence dials in. It stops being latent the
moment Subsample does, and #2075's page model already carries an `app` on every
page for exactly this reason: the information needed to fix it is already on the
wire and is being discarded. A control should be addressed by the app that
declared it, which the manifest already says.

### 4. Two tests assert what the page does rather than what it should do

`tests/test_page.py` — test quality

`test_the_playhead_cannot_widen_the_page_as_it_wraps` asserts that
`.part-body` computes `overflow: hidden`, and
`test_only_one_scrollbar_and_it_is_ours` asserts `scrollbar-width: none`. Both
restate a line of the stylesheet rather than the behaviour it exists for. Either
would keep passing if the behaviour broke by another route, and both would fail
on a correct change of technique.

They were written when no browser could run them and a proxy was the only thing
available. That is no longer true: the first can be written as "after the
playhead has wrapped, the document is no wider than the viewport", and the
second as "there is exactly one element in the block that scrolls".

### 5. `arrange` is the one frame the service accepts without looking at it

`superintendent/hub.py:160`, `superintendent/subsequence_adapter.py:_keep_arrangement`

Every other panel-to-app frame is checked somewhere: a `set` is validated by the
control that owns the path, and its shape is checked again when the service
mirrors the reported change. An `arrange` frame is forwarded whole and written to
disk by the adapter without either end looking at `parts`.

There is no path traversal here — the page id is a JSON key, not a filename —
so this is not a security finding on a LAN. It is a robustness one: a malformed
`parts` list is persisted beside the composition and handed back to every panel
on the next declaration, where the client reads `.name`, `.x` and `.y` off
whatever it finds. A page that cannot be drawn would then survive a restart.
Validating the shape where it is written is a few lines.

---

## Low

### 6. The playhead rebuilds its animation loop twice a second

`superintendent/client/app.js:739` — carried over from the first review, still true

`anchor` is in the effect's dependencies, so every beat cancels the
`requestAnimationFrame` chain and starts another. Harmless at one playhead per
page; less so with several parts on a page, which is now the ordinary case.

### 7. A note's velocity is checked in a variable called `length`

`superintendent/subsequence_adapter.py:NoteGrid._shape`

The velocity branch reuses the name from the branch above it. It behaves
correctly and reads as though it does not.

### 8. An emptied row is forgotten by the service and remembered by the app

`superintendent/subsequence_adapter.py:NoteGrid.apply`

`controls._apply_note` removes a row from the service's copy once its last note
goes; the adapter leaves an empty dict in `composition.data`. The snapshot
filters empties, so nothing on the wire differs and no behaviour is wrong — but
the two copies of the same structure drift, and a future reader comparing them
will lose time. One line, for symmetry rather than for a bug.

### 9. Two refusals of the same thing are worded differently

`superintendent/hub.py:175`, `:194`

`arrange_requested` says `'subsequence' is not connected` and `set_requested`
says `subsequence is not connected`. A person sees these in the bar.

### 10. The startup line still cannot be typed into a panel

`superintendent/cli.py:_reachable_host` — carried over, unchanged

Binding every interface prints `http://<this machine>:8090/`. The service knows
its own addresses.

---

## Open Questions

- **Should *fit the glass* mean "fit what is arranged" or "fit what is
  declared"?** Finding 2 recommends freezing the fit during a drag, which
  settles the symptom. It does not settle what should happen when a person
  arranges a page that no longer fits and then leaves arrange mode: shrink to
  fit, or keep the size and scroll? #2072 says scroll, but it was answered
  before *fit* existed as a setting, and *fit* is the one choice that means the
  opposite.
- **Does a settings block belong on the lattice at all?** Finding 1 is a
  collision between "a block measures whole cells" and "a control is pressable".
  Growing the row track resolves it, but a settings block is the first control
  whose natural size has nothing to do with the step grid's rhythm, and there
  will be more of those.
- **Is 5 s still the right pending timeout?** Unchanged from the first review
  and still unchecked against the panel's Wi-Fi (#2003).

## Not Issues

Beyond those in the first review, which still stand:

- **`Params.poll()` returning `[]` while doing work.** It looks like a polling
  method that reports nothing. It is the app telling the *instrument* rather
  than telling a panel, and the panel already has the values from the snapshot.
  The docstring says so and should stay.
- **The client's `kinds` ref rather than reading `controls` in the frame
  handler.** Deliberate: the handler is built once, so anything it closed over
  at mount would be the empty declarations it had then. A neighbouring comment
  already warns about exactly this and was written before the trap was fallen
  into a second time.
- **`Window` left unpositioned while its track is absolute.** Load-bearing: the
  playhead measures its offset against the block's body, and a positioned
  scroller would insert itself into that chain. Commented at the site.
- **Blocks rendered in declaration order rather than stacking order.** Looks
  like a bug — the array called `stacked` is not the array being mapped. It is
  the fix for a real defect: moving a node releases pointer capture, so a drag
  died after its first pixel. Commented at the site, and covered by
  `test_a_block_is_dragged_by_its_title_a_cell_at_a_time`.
- **`_on_a_loop` in the adapter tests spawning a thread.** Not ceremony: once a
  browser exists in the session Playwright holds a loop on the main thread, and
  a second cannot be started inside it. It is also what the composition's clock
  actually is.


---

## What was done, same day

Every finding above is fixed except where noted, and one more was found on the
way by the test written for finding 4.

| | |
| --- | --- |
| 1 | Params rows grow to hold their contents, and the fit is told the floor so a block measures as tall as it draws. Regression test at compact. |
| 2 | The fit solves for the arrangement as it stood when arranging began, and catches up once on leaving — which is also when it is saved. Regression test asserts the cell size does not move under a drag. |
| 3 | A page's parts and taps go to the app that declared the page. Behaviour is unchanged today, since one app dials in; the wrong-app hazard is gone. Parts from two different apps on one page remain out of scope. |
| 4 | Both proxy tests replaced by behavioural ones. |
| 5 | An arrangement is reduced to what a panel could draw before it is written, and refused with a reason if it cannot be. |
| 6 | The playhead holds its anchor in a ref and builds its animation once per part rather than twice a second. |
| 7, 8, 9 | Done as described. |
| 10 | The startup line prints the address the machine would be reached on — 192.168.0.146 here, rather than "&lt;this machine&gt;". |

**Found by finding 4's replacement**, and worth the exercise on its own: the
header bar hung 93 px past the edge of a 1280-wide viewport, giving the whole
document a horizontal scrollbar. It is the same fault Simon reported for the
playhead, from an unrelated cause — the header holds a transport, a button per
page, the size chooser and the version, and on a narrow panel that is more than
one line. It now wraps. The proxy test it replaced asserted a line of the
stylesheet and could never have seen it.

162 tests pass, none skipped.
