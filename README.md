# afb-test-py

Unit test framework for AFB bindings.

This repository provides a small set of functions and classes to help you write
unit tests for an AFB binding, on top of Python’s standard `unittest` module.

It is designed to work seamlessly with the AFB framework by running each test
inside its own AFB binder event loop.

## Dependencies

- Python 3
- `afb-libpython` installed and importable as `libafb` (native Python module)
- your AFB binding `.so` files and their runtime dependencies must be reachable
  by the dynamic linker (system install or `LD_LIBRARY_PATH`)

## Install

This project is a pure Python package (module name: `afb_test`).

### Install from source (system / virtualenv)

```bash
python3 -m pip install .
```

### User install (no root)

```bash
python3 -m pip install --user .
```

### Development install (editable)

```bash
python3 -m pip install -e .
```

### Quick import check

```bash
python3 -c "import afb_test; import libafb; print('afb_test and libafb import OK')"
```

## Helpers supplied

The `AFBTestCase` provides a `unittest.TestCase` base class with:

- additional assertion helpers specific to AFB (e.g. `assertEventEmitted`)
- a wrapper ensuring a fresh AFB binder event loop is started for each test, and
  that each test is executed inside that loop

The function `configure_afb_binding_tests` creates the global test configuration
(bindings list and binder config injection).

The function `run_afb_binding_tests` is intended for test scripts executed via
`__main__`. It provides additional command-line arguments such as TAP output.

## Minimal example

```python
from afb_test import AFBTestCase, configure_afb_binding_tests, run_afb_binding_tests
import libafb

# binding UID -> path to .so
# "path" can be a filename if the dynamic linker can resolve it (e.g. via LD_LIBRARY_PATH)
bindings = {"mybinding": "mybinding.so"}

def setUpModule():
    configure_afb_binding_tests(
        bindings=bindings,
        # This dict is injected into the binder "set" configuration field.
        # Use it to pass configuration to your bindings if they read it from the binder.
        config={
            "mybinding.so": {
                "$schema": "http://iot.bzh/download/public/schema/json/ctl-schema.json",
                "metadata": {},
                "mybinding": [],
            }
        },
    )

class TestMyBinding(AFBTestCase):
    def test_ping_verb(self):
        """Test ping verb"""
        r = libafb.callsync(self.binder, "mybinding", "ping")
        assert r.args == ("Pong!",)

if __name__ == "__main__":
    run_afb_binding_tests(bindings)
```

## Running tests

### With unittest (no extra CLI options)

`AFBTestCase` is compatible with `unittest` discovery. Example:

```bash
python3 -m unittest -v
```

### Direct invocation (enables extra CLI options)

If you use `run_afb_binding_tests()` in your `__main__`, you can run your test
file directly:

```bash
python3 path/to/test_my_binding.py
```

## Additional command line options

These options are **only** available through direct invocation (i.e. using
`run_afb_binding_tests()`), not through `python -m unittest`.

- `--tap`: output test results in [TAP](https://testanything.org/) format

## Environment variables

Bindings’ `.so` files are searched for in the system library path. If your
bindings are built locally, you typically need to extend the dynamic linker
search path, for example:

```bash
LD_LIBRARY_PATH=./build python3 -m unittest -v
```

You may also need to extend `LD_LIBRARY_PATH` to include runtime dependencies of
your binding (and/or `libafb` / `libafb-binder`) if they are not installed in
standard locations.
