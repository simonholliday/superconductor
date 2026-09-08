"""The package imports and carries its docstring."""

import superconductor


def test_package_imports () -> None:
	"""The package is importable and documented."""
	assert superconductor.__doc__ is not None
