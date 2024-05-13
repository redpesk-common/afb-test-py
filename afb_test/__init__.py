import os
import sys
import traceback
import unittest

from contextlib import contextmanager
from typing import Optional

import libafb

_binder = None


class AFBTestCase(unittest.TestCase):
    """A base class for an AFB unit test. It makes sure the binder
    exists through self.binder and offers some helper methods"""

    def run(self, result=None):
        """Makes sure each test is launched in the main event loop"""
        global _binder
        self.binder = _binder

        def _cb(binder, _):
            # call the actual test method
            unittest.TestCase.run(self, result)

            # aborts the loop
            return 1

        libafb.loopstart(_binder, _cb, None)

    @contextmanager
    def assertEventEmitted(self, api: str, event_name: str):
        """Helper context manager that allows to easily test that an event has been effectively called"""
        evt_received = False

        def on_evt(*args):
            nonlocal evt_received
            evt_received = True

        handler = libafb.evthandler(
            self.binder,
            {"uid": api, "pattern": f"{api}/{event_name}", "callback": on_evt},
        )

        yield

        assert evt_received


class TAPTestResult(unittest.result.TestResult):
    """TestResult class that outputs test results in the TAP format"""

    def __init__(self, n_tests: int, stream=None):
        super().__init__()
        self.n_tests = n_tests
        self.stream = stream or sys.stdout

        self.stream.write(f"1..{self.n_tests}\n")
        self.stream.flush()

        self.test_n = 0

    def addSuccess(self, test):
        self.stream.write(f"ok {self.test_n} - {test.shortDescription()}\n")
        self.stream.flush()
        self.test_n += 1

    def addError(self, test, err):
        exc_type, exc, tb = err
        self.stream.write(
            f"not ok {self.test_n} - {test.shortDescription()} # Exception:\n"
        )
        traceback.print_exception(exc_type, exc, tb, file=self.stream)
        self.stream.flush()
        self.test_n += 1

    def addFailure(self, test, err):
        self.addError(test, err)


class TAPTestRunner:
    def run(self, test):
        result = TAPTestResult(test.countTestCases())

        test(result)

        return result


class AFBTestProgram(unittest.TestProgram):
    """Main test program

    It allows us to add new command line arguments to the default ones
    provided by unittest.
    """

    def _getParentArgParser(self):
        parser = super()._getParentArgParser()
        parser.add_argument(
            "--tap",
            action="store_true",
            dest="tap_format",
            help="Use TAP as output format",
        )
        parser.add_argument(
            "--path",
            dest="so_path",
            help="Path where bindings' .so files are looking for",
        )
        return parser
    
    def runTests(self, skip=True) -> None:
        if not skip:
            return super().runTests()


def run_afb_binding_tests(bindings: dict, config: Optional[dict] = None):
    """Main test function to be called in __main__"""
    global _binder

    tp = AFBTestProgram()

    configure_afb_binding_tests(bindings, config, tp.so_path)

    tp.runTests(skip=False)


def configure_afb_binding_tests(bindings: dict, config: Optional[dict] = None, path: Optional[str] = None):
    """Configuration function to be called when tests are set up.
    
    When unittest is launched with python -m unittest, the only way to
    pass it options is through the use of environment variables.
    TEST_BINDING_PATH is then used here to point to the path where
    bindings' .so files are located"""
    global _binder

    # We cannot have more than one binder
    if _binder:
        return

    _binder = libafb.binder(
        {
            "uid": "py-binder",
            "verbose": 255,
            "rootdir": ".",
            "set": config or {},
            # do not open a listening TCP socket for tests
            "port": 0,
        }
    )

    so_path = os.environ.get("TEST_BINDING_PATH","") or path or ""

    for binding_uid, path in bindings.items():
        libafb.binding(
            {
                "uid": binding_uid,
                "path": os.path.join(so_path, path),
            }
        )
