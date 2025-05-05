import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--all", action="store_true", help="run all tests, including slow ones"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--all"):
        skip_integration = pytest.mark.skip(reason="need --all option to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: mark test as integration test")
