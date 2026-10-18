"""Raw Redis access using the same URL as Django's default cache."""
from functools import lru_cache

import redis
from django.conf import settings


@lru_cache(maxsize=4)
def get_redis_connection(alias='default'):
    config = settings.CACHES[alias]
    if config['BACKEND'] != 'django.core.cache.backends.redis.RedisCache':
        raise ValueError('Raw Redis access requires the Redis cache backend')
    return redis.Redis.from_url(config['LOCATION'], socket_connect_timeout=3, socket_timeout=5)
