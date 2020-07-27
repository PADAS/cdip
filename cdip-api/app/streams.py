import walrus

import app.settings

POSITIONS_STREAM_KEY = app.settings.POSITIONS_STREAM_KEY

async def get_position_stream():
    try:
        yield walrus.Database(host=app.settings.REDIS_HOST, port=app.settings.REDIS_PORT,
                              db=app.settings.REDIS_DB).Stream(POSITIONS_STREAM_KEY)
    finally:
        pass

