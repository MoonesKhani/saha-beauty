"""Explicit database preparation; starting the web server never seeds or overwrites content."""
import argparse
import json
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from .config import Settings, ROOT
from .db import make_engine
from .models import Service, TeamMember


def upgrade_database(url):
    parsed = make_url(url)
    if parsed.drivername.startswith('sqlite') and parsed.database and parsed.database != ':memory:':
        Path(parsed.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(ROOT / 'database' / 'alembic.ini'))
    config.attributes['database_url'] = url
    command.upgrade(config, 'head')


def seed_database(url):
    data = json.loads((ROOT / 'database' / 'seed.json').read_text())
    engine = make_engine(url)
    try:
        with Session(engine) as db, db.begin():
            for model, key in [(Service, 'services'), (TeamMember, 'team')]:
                for row in data[key]:
                    if db.get(model, row['code']) is None:
                        db.add(model(**row))
    finally:
        engine.dispose()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='مدیریت ساختار پایگاه داده سها')
    parser.add_argument('command', choices=['init-db', 'migrate', 'seed'])
    args = parser.parse_args()
    url = Settings().database_url
    if args.command in ('init-db', 'migrate'):
        upgrade_database(url)
    if args.command in ('init-db', 'seed'):
        seed_database(url)
    print('عملیات پایگاه داده انجام شد.')
