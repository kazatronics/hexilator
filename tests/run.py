# SPDX-License-Identifier: Apache-2.0
"""Test runner, executed by freecadcmd (see mise-tasks/test).

freecadcmd exits 0 even when a script raises, so the outcome goes to $HEXILATOR_RESULT.
"""

import os
import sys
import traceback
import unittest

root = os.environ["HEXILATOR_ROOT"]
result_path = os.environ["HEXILATOR_RESULT"]
pattern = os.environ.get("HEXILATOR_PATTERN", "test_*.py")
if not pattern.endswith(".py"):
    pattern += ".py"
tests_dir = os.path.join(root, "tests")
sys.path.insert(0, tests_dir)

ok = False
try:
    suite = unittest.TestLoader().discover(tests_dir, pattern=pattern, top_level_dir=tests_dir)
    res = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    ok = res.wasSuccessful() and res.testsRun > 0
    if res.testsRun == 0:
        print("no tests matched %r" % pattern)
except Exception:
    traceback.print_exc()
with open(result_path, "w") as f:
    f.write("ok" if ok else "fail")
