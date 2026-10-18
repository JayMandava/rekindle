import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from rekindle.config import Merchant, Settings
from rekindle.engine import Engine

AS_OF = date(2026, 10, 18)


@pytest.fixture
def merchant():
    return Merchant()


@pytest.fixture
def engine():
    return Engine.build(Settings(mode="local", send_mode="dry_run", chaos=0.0, as_of=AS_OF))
