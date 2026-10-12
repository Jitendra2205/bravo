"""Pill labels (pure logic; drawing needs a display)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    import tkinter  # noqa: F401  (bundled on Windows; some Linux images lack it)
except ImportError:
    import types
    sys.modules["tkinter"] = types.SimpleNamespace(Tk=None, Canvas=None, TclError=Exception)
import pill  # noqa: E402


class PillText(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(pill.label_for("listening", "agent"), "Ask Awaaz")
        self.assertEqual(pill.label_for("working", "dictate"), "Transcribing")
        self.assertEqual(pill.label_for("idle", "dictate"), "Awaaz")
        self.assertEqual(pill.label_for("error", "agent", "No microphone found"), "No microphone found")
        self.assertEqual(pill.hint_for("listening"), "release to finish")
        self.assertEqual(pill.hint_for("done"), "")


if __name__ == "__main__":
    unittest.main()
