"""Test runner adapted to Neon's managed PostgreSQL.

`manage.py test --parallel` builds one template database and then clones it
once per worker with `CREATE DATABASE ... TEMPLATE test_neondb`. PostgreSQL
refuses that statement while any session is connected to the template, so
Django's PostgreSQL backend closes its own connection and its pool immediately
before cloning:

    # CREATE DATABASE ... WITH TEMPLATE ... requires closing connections
    # to the template database.
    self.connection.close()
    self.connection.close_pool()

Against a local PostgreSQL that is enough. Against Neon it is not, and the run
dies during setup with

    source database "test_neondb" is being accessed by other users
    DETAIL:  There is 1 other session using the database.

This module exists because that failure has two causes, only one of which is
fixable from here, and because the unfixable one deserves an error message that
says so instead of a stack trace.

**Cause one — a real lingering session.** `create_test_db` deliberately ends
with `self.connection.ensure_connection()`, and Neon does not reap the
server-side backend the moment the client socket closes. Instrumenting the
first clone showed exactly one `idle` client backend still attached to the
template. Terminating it before cloning fixes that, and this runner does.

**Cause two — a session that does not exist.** With the first cause handled,
later clones still failed. Probed from a clean psycopg connection, with nothing
of ours running:

    current_user: neondb_owner
    is_superuser: False
    sessions on test_neondb: []
    after terminate:         []
    CREATE DATABASE test_probe TEMPLATE test_neondb
      -> source database "test_neondb" is being accessed by other users
         DETAIL:  There is 1 other session using the database.

`pg_stat_activity` reports no sessions, `pg_terminate_backend` has nothing to
terminate, and the server refuses the clone anyway. The holder is internal to
Neon and invisible to `neondb_owner`, which is not a superuser and so cannot
see or signal it. No amount of closing, waiting or retrying reaches it.

So parallel cloning is not available on this database, and pretending otherwise
just costs a confusing failure during setup. Run the suite with the default
`--parallel 1`. It is slower — the cost is network latency per query against a
remote database, not the runner — but it completes. Against a local PostgreSQL
or a Neon role with superuser rights, `--parallel` works and this runner stays
out of the way.
"""

from django.conf import settings
from django.db import connections
from django.db.backends.base.creation import TEST_DATABASE_PREFIX
from django.test.runner import DiscoverRunner

CLONE_UNAVAILABLE_HELP = (
    'Cloning the test database failed. On Neon this is expected: a connection '
    'internal to the service holds the template, and `neondb_owner` is not a '
    'superuser, so it is neither visible in pg_stat_activity nor reachable by '
    'pg_terminate_backend. Re-run without --parallel (or with --parallel 1). '
    'See config/test_runner.py for the evidence behind this.'
)


def _assert_is_generated_test_database(database_name, application_database):
    """Refuse to act on anything but a test database Django just generated.

    `application_database` must be the name read *before* database setup:
    `create_test_db` rewrites `settings.DATABASES[alias]['NAME']` to the test
    database as one of its first acts, so reading it at clone time would
    compare the template against itself and this check would never pass.
    """
    if (
        not database_name
        or database_name == application_database
        or not database_name.startswith(TEST_DATABASE_PREFIX)
    ):
        raise RuntimeError(
            f'refusing to act on {database_name!r}: it is not a generated test database'
        )


def _terminate_sessions_on(connection, database_name):
    """Disconnect anything still attached to `database_name`.

    Uses the backend's no-database cursor, which connects to the maintenance
    database rather than to the target, so this never terminates its own
    session — and the `pid <> pg_backend_pid()` clause makes that explicit
    even if the fallback path ever connects somewhere else.
    """
    with connection._nodb_cursor() as cursor:
        cursor.execute(
            'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
            'WHERE datname = %s AND pid <> pg_backend_pid()',
            [database_name],
        )


class NeonDiscoverRunner(DiscoverRunner):
    """`DiscoverRunner`, with the template released before each clone."""

    def setup_databases(self, **kwargs):
        patched = []

        for connection in connections.all():
            if connection.vendor != 'postgresql':
                continue

            creation = connection.creation
            original_clone = creation.clone_test_db
            # Read now, before `create_test_db` rewrites it to the test name.
            application_database = settings.DATABASES[connection.alias].get('NAME')

            def clone_test_db(
                suffix,
                *args,
                _creation=creation,
                _original=original_clone,
                _application_database=application_database,
                **clone_kwargs,
            ):
                # `NAME` is the template here: Django rewrote it when it
                # created the test database.
                template = _creation.connection.settings_dict['NAME']
                _assert_is_generated_test_database(template, _application_database)
                _terminate_sessions_on(_creation.connection, template)

                try:
                    return _original(suffix, *args, **clone_kwargs)
                except SystemExit as exit_error:
                    # `_execute_create_test_db` logs and calls sys.exit(2)
                    # rather than raising, so a refusal arrives as SystemExit.
                    # Replace it with something that says what to do.
                    raise RuntimeError(CLONE_UNAVAILABLE_HELP) from exit_error

            creation.clone_test_db = clone_test_db
            patched.append((creation, original_clone))

        try:
            return super().setup_databases(**kwargs)
        finally:
            # Leave the connection objects as they were found; a test that
            # inspects them should not see this adapter.
            for creation, original_clone in patched:
                creation.clone_test_db = original_clone
