# afb-test-py

Unit test framework for AFB bindings.

This repository contains a small set of functions and classes to help you write unit tests for an AFB binding.

The `unittest` standard Python module is used as a base for the unit test framework. It is extended a bit here to work seamlessly with the AFB framework.

## Helpers supplied

The `AFBTestCase` provides a `unittest.TestCase` class with:
- some additional assertion methods specific to AFB (e.g. `assertsEventEmitted`)
- a small wrapper to make sure an new event loop is started at the
  beginning of each test, and that each test is executed inside the loop

The function `configure_afb_binding_tests` will create the global binder and load bindings. It is possible to pass a configuration for a binding through the `config` parameter.

The function `run_afb_binding_tests` is to be used when tests are launched as a main. It offers additional command line arguments to specify a path for binding .so files or the TAP format for formatting test outputs

## Minimal example

```python
from afb_test import AFBTestCase, configure_afb_binding_tests, run_afb_binding_tests

import libafb

bindings = {"mybinding": f"mybinding.so"}

def setUpModule():
    configure_afb_binding_tests(
        bindings=bindings,
        config={"mybinding.so": {
            "$schema": "http://iot.bzh/download/public/schema/json/ctl-schema.json",
            "metadata": {...}
            "mybinding": [...]})

class TestMyBinding(AFBTestCase):

    def test_ping_verb(self):
        """Test ping verb"""
        r = libafb.callsync(self.binder, "mybinding", "ping")
        assert r.args == ("Pong!",)

if __name__ == "__main__":
    run_afb_binding_tests(bindings)
```

## Additional command line options

**Only available through direct invocation**, not through `python -m unittest`

- `--tap`: output test results in [TAP](https://testanything.org/) format
- `--path <path>`: sepcifies a path to look for binding's .so files

## Environement variables

- `TEST_BINDING_PATH`: this variable can be used to specify the path where binding's .so files are searched for. The environment variable is the only to specify such path when tests are launched through the `unittest` module (e.g. `python -m unittest`).