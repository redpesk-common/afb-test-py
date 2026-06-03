import json
import os
import sys
import traceback
import unittest

from contextlib import contextmanager
from typing import Optional

import libafb

_binder_config = {}
_bindings = {}
_binder_debug = os.environ.get("AFB_TEST_DEBUG", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

_UNSET = object()


class EventAssertionError(AssertionError):
    pass


def serialize_test_case_result(result: unittest.TestResult):
    """Serialize a TestResult into a JSON-dumpable dict."""

    # TestResult stores errors and failures as tuple of the form
    # (test_case, error_string) where test_case is the instance of the
    # TestCase. This is not serializable as is, but we assume the
    # unserialization part knows which test case it is.
    return {
        "failfast": result.failfast,
        "failures": [f[1] for f in result.failures],
        "errors": [f[1] for f in result.errors],
        "testsRun": result.testsRun,
        "skipped": bool(len(result.skipped)),
        "expectedFailures": [f[1] for f in result.expectedFailures],
        "unexpectedSuccesses": bool(len(result.unexpectedSuccesses)),
        "shouldStop": result.shouldStop,
        "buffer": result.buffer,
        "tb_locals": result.tb_locals,
        "_mirrorOutput": result._mirrorOutput,
    }


def unserialize_in_result(
    result: unittest.TestResult, result_json, test_case: unittest.TestCase
):
    for attr in (
        "failfast",
        "testsRun",
        "shouldStop",
        "buffer",
        "tb_locals",
        "_mirrorOutput",
    ):
        setattr(result, attr, result_json[attr])

    result.failures += [(test_case, err) for err in result_json["failures"]]
    result.errors += [(test_case, err) for err in result_json["errors"]]
    result.expectedFailures += [
        (test_case, err) for err in result_json["expectedFailures"]
    ]
    result.unexpectedSuccesses += (
        [test_case] if result_json["unexpectedSuccesses"] else []
    )
    result.skipped += [test_case] if result_json["skipped"] else []


class AFBTestCase(unittest.TestCase):
    """A base class for an AFB unit test. It makes sure the binder
    exists through self.binder and offers some helper methods"""

    def run(self, result=None):
        """Makes sure each test is launched in the main event loop"""
        global _binder_config, _bindings
        self._result = None

        def _cb(binder, _):
            # call the actual test method
            unittest.TestCase.run(self, result)
            self._result = result

            # aborts the loop
            return 1

        # afb-binder is not designed to have an event loop started,
        # then stopped, then started for each test. We then fork() for
        # each test and create a binder and an event loop each time

        pipe_r, pipe_w = os.pipe()

        pid = os.fork()
        if pid == 0:
            # child
            os.close(pipe_r)
            binder_config = {
                "uid": "py-binder",
                "verbose": 255,
                "rootdir": ".",
                "set": _binder_config or {},
                # do not open a listening TCP socket for tests
                "port": 0,
            }

            if _binder_debug:
                # Keep the binder alive and let the debugger catch faults.
                binder_config.update(
                    {
                        "timeout": 0,
                        "trapfaults": False,
                    }
                )

            _binder = libafb.binder(binder_config)

            for binding_uid, path in _bindings.items():
                libafb.binding(
                    {
                        "uid": binding_uid,
                        # Defining LD_LIBRARY_PATH might be needed to find .so files
                        "path": path,
                    }
                )

            self.binder = _binder

            r = libafb.loopstart(_binder, _cb, None)

            os.write(
                pipe_w,
                json.dumps(serialize_test_case_result(self._result)).encode("utf-8"),
            )
            os.close(pipe_w)
            sys.exit(r)
        else:
            os.close(pipe_w)
            pipe_r = os.fdopen(pipe_r)
            unserialize_in_result(result, json.loads(pipe_r.read()), self)
            pipe_r.close()
            os.waitpid(pid, 0)

    @contextmanager
    def assertEventEmitted(
        self,
        api: str,
        event_name: str,
        timeout_ms: int = 100,
        value=_UNSET,
        value_lambda=None,
    ):
        """Helper context manager that allows to easily test that an event has been effectively called"""
        import time

        evt_received = False
        list_data = None

        def on_evt(*args):
            nonlocal evt_received, list_data
            evt_received = True
            _capsule, _event, _unused, *list_data = args

        libafb.evthandler(
            self.binder,
            {"pattern": f"{api}/{event_name}", "callback": on_evt},
        )
        try:
            yield

            start = time.monotonic()
            while (
                time.monotonic() - start
            ) * 1000.0 <= timeout_ms and not evt_received:
                time.sleep(0.01)

            if not evt_received:
                raise EventAssertionError(
                    f"No event received within {timeout_ms} ms for pattern '{api}/{event_name}'."
                )

            if value is not _UNSET and len(list_data) > 0:
                got_value = (
                    value_lambda(list_data[0])
                    if value_lambda is not None
                    else list_data[0]
                )

                self.assertEqual(
                    got_value,
                    value,
                    msg=(
                        f"Event received but payload value mismatch for pattern '{api}/{event_name}'.\n"
                        f"Expected value: {value!r}\n"
                        f"Got value:      {got_value!r}\n"
                        f"Full payload:   {list_data!r}"
                    ),
                )

        finally:
            libafb.evtdelete(self.binder, f"{api}/{event_name}")


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
        self.stream.write(
            f"ok {self.test_n} - {test.shortDescription() or test.id()}\n"
        )
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
        super().addError(test, err)

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
            "--afb-debug",
            action="store_true",
            dest="afb_debug",
            default=False,
            help=(
                "Enable debug-friendly binder settings for tests "
                "(timeout=0, trapfaults=False). Can also be enabled with "
                "AFB_TEST_DEBUG=1."
            ),
        )

        return parser

    def runTests(self, skip=True) -> None:
        global _binder_debug

        _binder_debug = _binder_debug or bool(getattr(self, "afb_debug", False))

        if not skip:
            return super().runTests()


def run_afb_binding_tests(bindings: dict, config: Optional[dict] = None):
    """Main test function to be called in __main__"""
    global _binder

    tp = AFBTestProgram(testRunner=TAPTestRunner() if "--tap" in sys.argv else None)

    configure_afb_binding_tests(bindings, config)

    tp.runTests(skip=False)


def configure_afb_binding_tests(bindings: dict, config: Optional[dict] = None):
    """Configuration function to be called when tests are set up."""

    global _binder_config
    global _bindings

    _bindings = bindings
    _binder_config = config
