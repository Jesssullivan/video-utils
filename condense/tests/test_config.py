"""The defaults are bounded, and every tool call has a timeout."""

import sys

import pytest

from condense import config


def test_default_parallelism_is_bounded():
    assert config.ENCODE["jobs"] == 2
    assert config.WHISPER["threads"] == 4


def test_a_tool_that_overruns_its_timeout_raises():
    with pytest.raises(RuntimeError, match="ran over 0.2 s"):
        config.run(sys.executable, "-c", "import time; time.sleep(5)", timeout=0.2)


def test_a_failing_tool_raises_with_its_stderr():
    with pytest.raises(RuntimeError, match="boom"):
        config.run(sys.executable, "-c", "import sys; sys.exit('boom')")
