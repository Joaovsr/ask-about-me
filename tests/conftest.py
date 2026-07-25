import os

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return os.getenv(
        "AAM_TEST_DATABASE_URL",
        "postgresql+psycopg://ask_about_me:ask_about_me@localhost:5433/ask_about_me_test",
    )
