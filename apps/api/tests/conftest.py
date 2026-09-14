import os
from pathlib import Path
from uuid import uuid4

import pytest

TEST_DATABASE = Path("/tmp") / f"pebs_purchase_test_{uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE}"


@pytest.fixture(scope="session", autouse=True)
def isolated_database():
    yield
    TEST_DATABASE.unlink(missing_ok=True)
