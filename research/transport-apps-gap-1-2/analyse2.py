"""Research prototype, not house style.  Prints block F's rows for the body."""

import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "results/ws_coalesce_bench2.jsonl"
rows = [json.loads(l) for l in open(path)]
print(len(rows), "rows")
for i, r in enumerate(rows):
	print(
		i, r.get("tag"), r.get("scenario"), "|", r.get("traffic"),
		"| sel", r.get("selector"), "spin", r.get("spin_ms"),
		"| in", r.get("inbound"), "app", r.get("applied"),
		"wk", r.get("wakeups"), "mpw", r.get("msgs_per_wakeup"),
		"bmax", r.get("batch_max"), "bmean", r.get("batch_mean_nonempty"),
		"| p99", r.get("p99_ms"), "max", r.get("max_ms"), "o1", r.get("over_1ms"),
		"mean", r.get("mean_ms"),
		"| cmed", r.get("cross_median_ms"), "cp99", r.get("cross_p99_ms"),
		"cmax", r.get("cross_max_ms"), "c>10", r.get("cross_over_10ms"),
		"cn", r.get("cross_n"),
		"| load", r.get("loadavg_start"), r.get("loadavg_end"),
	)
