# Theme separation: which instrument, and is ours the right one

Produced on 2026-09-12 for Subroutine **#2297**. The conclusions are there, and in the
docstring of `tools/theme_separation.py`; this directory holds only the instruments.

| File | What it does |
| --- | --- |
| `which_instrument.py` | Tries 8 colour-vision simulations x 4 distance measures x 2 readings of *worst* against the separation row #2190 published, on the exact colours it measured. None of the 64 came within 0.05 of it. |
| `extract_brettel.py` | Pulls Brettel, Viénot & Mollon 1997's precomputed parameters out of DaltonLens at full precision: the constants `tools/theme_separation.py` carries. |
| `verify_brettel.py` | Checks a pure-Python Brettel against DaltonLens across 20,024 colours and all three dichromacies. On 2026-09-12 the largest difference in linear RGB was 2.1e-15. **Run this before changing any constant in the tool.** |

They need DaltonLens and NumPy, which the project deliberately does not depend on, so run
them from a throwaway environment off the CIFS mount:

    python3 -m venv /tmp/daltonlens && /tmp/daltonlens/bin/pip install daltonlens==0.1.5 numpy
    /tmp/daltonlens/bin/python verify_brettel.py

`verify_brettel.py` keeps its own copy of the constants, so a change to the tool has to be
made in both places for the check to mean anything.
