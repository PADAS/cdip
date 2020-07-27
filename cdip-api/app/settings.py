from environs import Env

env = Env()
env.read_env()

AUTH0_ALGORITHMS = env.list('AUTH0_ALGORITHMS')

AUTH0_API_AUDIENCE = env('AUTH0_API_AUDIENCE')
AUTH0_DOMAIN = env('AUTH0_DOMAIN')

OAUTH_TOKEN_URL = f"https://{AUTH0_DOMAIN}/oauth/token"

# Settings for stream, where this API writes.
REDIS_HOST = env.str('REDIS_HOST')
REDIS_PORT = env.int('REDIS_PORT', 6739)
REDIS_DB = env.int('REDIS_DB', 0)

# Application settings
POSITIONS_STREAM_KEY=env.str('POSITIONS_STREAM_KEY', 'positions')