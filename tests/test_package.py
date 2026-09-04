"""The package imports and carries its docstring."""

import superintendent


def test_package_imports () -> None:
	"""The package is importable and documented."""
	assert superintendent.__doc__ is not None
