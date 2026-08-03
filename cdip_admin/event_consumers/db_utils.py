from django.db import connections


def refresh_db_connections():
    """
    Close errored or expired DB connections so the next ORM call opens a
    fresh one. Equivalent to django.db.close_old_connections(), except it
    skips connections inside an atomic block — closing mid-transaction would
    break the transaction (pytest-django runs every test inside one).
    """
    for conn in connections.all(initialized_only=True):
        if not conn.in_atomic_block:
            conn.close_if_unusable_or_obsolete()
