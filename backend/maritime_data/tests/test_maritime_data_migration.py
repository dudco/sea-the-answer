from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from backend.maritime_data.scripts.migrate_maritime_data import migrate_settings, migrate_schema


def test_settings_keep_values_and_comments_and_are_idempotent():
    source = '# token\nROLE4_API_TOKEN=private-test-value\nDATABASE_URL=unchanged\n'
    result = migrate_settings(source)
    assert result == '# token\nMARITIME_DATA_API_TOKEN=private-test-value\nDATABASE_URL=unchanged\n'
    assert migrate_settings(result) == result


def test_settings_conflict_is_rejected_before_changes():
    with pytest.raises(ValueError, match='Conflicting'):
        migrate_settings('ROLE4_API_TOKEN=old\nMARITIME_DATA_API_TOKEN=new\n')


class Engine:
    dialect = SimpleNamespace(name='postgresql')
    def __init__(self, schemas):
        self.schemas = schemas
        self.statements = []
    @contextmanager
    def begin(self):
        yield self
    def execute(self, sql, params=None):
        self.statements.append(str(sql))
        return SimpleNamespace(scalars=lambda: self.schemas)


def test_schema_preview_and_apply_do_not_reload_records():
    engine = Engine(['role4'])
    assert migrate_schema(engine) == 'migration_required'
    assert not any('ALTER' in sql for sql in engine.statements)
    assert migrate_schema(engine, apply=True) == 'migrated'
    assert engine.statements[-1] == 'ALTER SCHEMA role4 RENAME TO maritime_data'
    assert not any('DROP' in sql or 'INSERT' in sql or 'DELETE' in sql for sql in engine.statements)


def test_schema_conflict_and_already_migrated():
    with pytest.raises(ValueError, match='Both schemas'):
        migrate_schema(Engine(['role4', 'maritime_data']), apply=True)
    engine = Engine(['maritime_data'])
    assert migrate_schema(engine, apply=True) == 'already_migrated'
    assert not any('ALTER' in sql for sql in engine.statements)
