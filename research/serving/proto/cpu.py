"""Prototype: print utime+stime seconds and RSS MB for a pid from /proc."""
import sys, os
pid = sys.argv[1]
with open(f"/proc/{pid}/stat") as f:
	parts = f.read().rsplit(")", 1)[1].split()
ticks = os.sysconf("SC_CLK_TCK")
cpu = (int(parts[11]) + int(parts[12])) / ticks
with open(f"/proc/{pid}/status") as f:
	rss = [l for l in f if l.startswith("VmRSS")][0].split()[1]
print(f"{cpu:.2f} {int(rss)//1024}")
