"""Future scheduler entrypoint; currently notification contract is unavailable, so no sends."""
from .config import Settings
from .db import make_engine
from .sms_provider import Melipayamak
from .sms_outbox import dispatch_one

if __name__ == '__main__':
    settings=Settings();engine=make_engine(settings.database_url)
    try:
        print(dispatch_one(engine,Melipayamak(settings),settings))
    finally:
        engine.dispose()
