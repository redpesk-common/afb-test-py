import os
import sys
import traceback
import unittest

from contextlib import contextmanager

import libafb

_binder = None


class AFBTestCase(unittest.TestCase):
    """A base class for an AFB unit test. It makes sure the binder exists through self.binder and offers some helper methods"""
    
    def __init__(self, *args):
        global _binder
        super().__init__(*args)
        self.binder = _binder

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

    It also changes a bit the behaviour of a test program so that actual
    tests are not launched before we get our main event loop running.
    And because this event loop is blocking we are forced to hack things
    a bit here ... So methods that are called by the constructor and
    would run tests immediately are here modified to do nothing. And
    they are called again in the callback of the main loop
    """
    def __init__(self, *args, **kwargs):
        # force exit=False
        super().__init__(*args, **kwargs, exit=False)

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

    def createTests(self, *args, **kwargs):
        """Overload of createTests. By default, it will do nothing,
        except if a new parameter 'in_afb_loop' is set to True"""

        if kwargs.get("in_afb_loop", False):
            del kwargs["in_afb_loop"]
            return super().createTests(*args, **kwargs)

    def runTests(self, in_afb_loop=False):
        """Overload of runTests. By default, it will do nothing,
        except if a new parameter 'in_afb_loop' is set to True"""

        if in_afb_loop:
            if self.tap_format:
                self.testRunner = TAPTestRunner()
            return super().runTests()


def _on_binder_init(binder, tp):
    # Call again methods that create and run tests
    tp.createTests(in_afb_loop=True)
    tp.runTests(in_afb_loop=True)

    # exits the event loop now
    return 1


def run_afb_binding_tests(bindings: dict):
    global _binder
    # tp is created first so that CLI argument are parsed first, and
    # some (e.g. --help) may exit here before the main loop is started
    tp = AFBTestProgram()

    _binder = libafb.binder(
        {
            "uid": "py-binder",
            "verbose": 255,
            "rootdir": ".",
        }
    )

    for binding_uid, path in bindings.items():
        libafb.binding(
            {
                "uid": binding_uid,
                "path": os.path.join(tp.so_path or "", path),
            }
        )

    libafb.loopstart(_binder, _on_binder_init, tp)
