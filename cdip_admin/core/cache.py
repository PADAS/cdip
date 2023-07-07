import walrus
from django.conf import settings


def get_redis_db():
    return walrus.Database(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
    )


def get_deduplication_db():
    return walrus.Database(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB + 1,
    )


def get_devicecache_db():
    return walrus.Database(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB + 2,
    )

