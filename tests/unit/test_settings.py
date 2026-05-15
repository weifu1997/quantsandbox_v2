from pathlib import Path

from app.config.settings import Settings


def test_settings_derive_default_paths_from_project_root() -> None:
    settings = Settings(project_root=Path('/tmp/qs-project'))
    assert settings.data_dir == Path('/tmp/qs-project/data')
    assert settings.db_path == Path('/tmp/qs-project/data/db/quantsandbox_v2.sqlite3')
    assert settings.reports_dir == Path('/tmp/qs-project/data/reports')
    assert settings.datasets_dir == Path('/tmp/qs-project/data/datasets')
    assert settings.cache_dir == Path('/tmp/qs-project/data/cache')


def test_settings_respect_explicit_data_dir_override() -> None:
    settings = Settings(project_root=Path('/tmp/qs-project'), data_dir=Path('/tmp/custom-data'))
    assert settings.data_dir == Path('/tmp/custom-data')
    assert settings.db_path == Path('/tmp/custom-data/db/quantsandbox_v2.sqlite3')
    assert settings.reports_dir == Path('/tmp/custom-data/reports')


def test_settings_respect_explicit_path_overrides() -> None:
    settings = Settings(
        project_root=Path('/tmp/qs-project'),
        data_dir=Path('/tmp/custom-data'),
        db_path=Path('/tmp/custom-db.sqlite3'),
        reports_dir=Path('/tmp/custom-reports'),
    )
    assert settings.db_path == Path('/tmp/custom-db.sqlite3')
    assert settings.reports_dir == Path('/tmp/custom-reports')
    assert settings.datasets_dir == Path('/tmp/custom-data/datasets')
    assert settings.cache_dir == Path('/tmp/custom-data/cache')
