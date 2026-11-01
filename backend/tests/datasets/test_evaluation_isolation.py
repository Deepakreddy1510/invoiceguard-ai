import pytest
from sqlalchemy import create_engine, text

from scripts.dataset_v2.isolation import DatabasePool, child_environment, validate_name


@pytest.mark.parametrize(
    "name",
    [
        "invoiceguard",
        "invoiceguard_test",
        "postgres",
        "ig_eval_v2_injected;DROP DATABASE invoiceguard",
        "ig_eval_v2_" + "a" * 23,
    ],
)
def test_reject_nonowned_target_names(name):
    with pytest.raises(ValueError):
        validate_name(name)


def test_refuse_application_database_in_child():
    with pytest.raises(ValueError):
        child_environment("postgresql+psycopg://localhost/invoiceguard", "/tmp", "fallback")


def test_drop_requires_invocation_ownership(database):
    with DatabasePool(database.url.render_as_string(hide_password=False)) as pool:
        with pytest.raises(ValueError):
            pool.drop("ig_eval_v2_" + "a" * 24)
        with pytest.raises(ValueError):
            pool.create("ig_eval_v2_" + "b" * 24)


def test_actual_disposable_database_lifecycle(database):
    with DatabasePool(database.url.render_as_string(hide_password=False)) as pool:
        name, url = pool.create()
        engine = create_engine(url)
        with engine.connect() as c:
            assert c.execute(text("SELECT current_database()")).scalar_one() == name
        engine.dispose()
        pool.drop(name)
        with pool.admin.connect() as c:
            assert (
                c.execute(
                    text("SELECT count(*) FROM pg_database WHERE datname=:n"), {"n": name}
                ).scalar_one()
                == 0
            )
        assert pool.owned == set()
