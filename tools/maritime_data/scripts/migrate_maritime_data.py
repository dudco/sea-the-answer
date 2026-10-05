"""Rename the legacy PostgreSQL schema without reloading or rewriting records."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

LEGACY_SCHEMA = 'role4'
SCHEMA = 'maritime_data'
ENV_KEYS = {'ROLE4_API_TOKEN': 'MARITIME_DATA_API_TOKEN',
            'ROLE4_TEST_DATABASE_URL': 'MARITIME_DATA_TEST_DATABASE_URL'}


def migrate_settings(source):
    """Keep secrets and unrelated settings unchanged; reject conflicting values."""
    entries = {}
    for line in source.splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            entries[key.strip()] = value
    for old, new in ENV_KEYS.items():
        if old in entries and new in entries and entries[old] != entries[new]:
            raise ValueError(f'Conflicting settings for {new}; no changes applied.')
    output = []
    for line in source.splitlines(keepends=True):
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            if key.strip() in ENV_KEYS:
                if ENV_KEYS[key.strip()] in entries:
                    continue
                line = ENV_KEYS[key.strip()] + '=' + value
        output.append(line)
    return ''.join(output)


def migrate_schema(engine, apply=False):
    if engine.dialect.name != 'postgresql':
        raise ValueError('This migration requires PostgreSQL.')
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        connection.execute(text("SET LOCAL statement_timeout = '30s'"))
        schemas = set(connection.execute(
            text('SELECT nspname FROM pg_namespace WHERE nspname IN (:old, :new)'),
            {'old': LEGACY_SCHEMA, 'new': SCHEMA}).scalars())
        if LEGACY_SCHEMA in schemas and SCHEMA in schemas:
            raise ValueError('Both schemas exist; refusing to combine or overwrite data.')
        if LEGACY_SCHEMA not in schemas:
            return 'already_migrated' if SCHEMA in schemas else 'no_dataset'
        if not apply:
            return 'migration_required'
        # Constant identifiers only. PostgreSQL preserves tables, views and grants.
        connection.execute(text('ALTER SCHEMA role4 RENAME TO maritime_data'))
        return 'migrated'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply the schema/settings rename')
    args = parser.parse_args()
    config = Path(__file__).resolve().parents[3] / '.env.local'
    source = config.read_text(encoding='utf-8') if config.exists() else ''
    settings = migrate_settings(source)  # Check conflicts before touching the DB.
    load_dotenv(config, override=False)
    url = os.getenv('DATABASE_URL', '')
    if not url:
        raise ValueError('DATABASE_URL is required in .env.local or the environment.')
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    engine = create_engine(url, hide_parameters=True, connect_args={'connect_timeout': 5})
    try:
        status = migrate_schema(engine, args.apply)
    finally:
        engine.dispose()
    if args.apply and settings != source:
        backup = config.with_name('.env.local.before-maritime-data')
        if not backup.exists():
            backup.write_text(source, encoding='utf-8')
        config.write_text(settings, encoding='utf-8')
    print(f'Schema status: {status}. Settings rename: ' +
          ('applied' if args.apply else 'preview only') + '.')
    print('No records were reloaded or rewritten. Dataset folders were left in place.')


if __name__ == '__main__':
    main()
