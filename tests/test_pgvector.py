import pytest
from sqlalchemy import create_engine, text


def test_migrated_postgres_supports_vector_distance(test_database_url: str) -> None:
    engine = create_engine(test_database_url)

    try:
        with engine.connect() as connection:
            distance = connection.scalar(text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector"))
    finally:
        engine.dispose()

    assert distance == pytest.approx(1.0)
