import re
import os
import logging
import functools

from bottle import request


POSTGRES_BACKEND = 'postgres'
SQLITE_BACKEND = 'sqlite'
SERVERLESS_DATABASE_BACKENDS = (SQLITE_BACKEND,)


def import_squery(conf):
    backend = conf['database.backend']
    if backend == SQLITE_BACKEND:
        from squery_lite.squery import Database, DatabaseContainer
    elif backend == POSTGRES_BACKEND:
        from squery_pg.squery_pg import Database, DatabaseContainer
    else:
        raise ValueError('Unknown database backend: {}'.format(backend))

    return (Database, DatabaseContainer)


def is_serverless(conf):
    return conf['database.backend'] in SERVERLESS_DATABASE_BACKENDS


def ensure_dir(path):
    """ Make sure directory at path exists """
    if not os.path.exists(path):
        os.makedirs(path)


def get_database_path(conf, name):
    return os.path.abspath(os.path.join(conf['database.path'], name + '.db'))


def patch_connection(backend, conn):
    """
    Adds database backend specific extra goodies
    """
    if backend == SQLITE_BACKEND:
        conn.create_function('REGEXP', 2, regexp_operator)


def get_databases(database_cls, container_cls, backend, db_confs, host, port,
                  user, password, debug=False):
    databases = {}
    for name, db_config in db_confs.items():
        conn = database_cls.connect(host=host,
                                    port=port,
                                    database=db_config['database'],
                                    user=user,
                                    password=password,
                                    debug=debug)
        patch_connection(backend, conn)
        databases[name] = conn
    return container_cls(databases, debug=debug)


def get_database_configs(conf):
    serverless = is_serverless(conf)
    databases = dict()
    for name in conf['database.names']:
        database = get_database_path(conf, name) if serverless else name
        databases[name] = dict(package_name='registry', database=database)
    return databases


def init_databases(config):
    (database_cls, container_cls) = import_squery(config)
    database_configs = get_database_configs(config)
    if is_serverless(config):
        # Make sure all necessary directories are present
        for db_config in database_configs.values():
            ensure_dir(os.path.dirname(db_config['database']))

    debug = config['server.debug']
    databases = get_databases(database_cls,
                              container_cls,
                              config['database.backend'],
                              database_configs,
                              config['database.host'],
                              config['database.port'],
                              config['database.user'],
                              config['database.password'],
                              debug=debug)
    # Run migrations on all databases
    for db_name, db_config in database_configs.items():
        migration_pkg = '{0}.migrations.{1}'.format(db_config['package_name'],
                                                    db_name)
        database_cls.migrate(databases[db_name], migration_pkg, config)

    return databases


def row_to_dict(row):
    return {col: row[col] for col in row.keys()}


def regexp_operator(expr, item):
    try:
        rx = re.compile(expr)
        return rx.search(item) is not None
    except Exception as e:
        logging.exception('Error while using REGEXP operator: {}'.format(e))


def pre_init(app, config):
    logging.info('Connecting to databases')
    databases = init_databases(config)
    config['database.connections'] = databases


def plugin(config):
    databases = config['database.connections']

    def db_plugin(callback):
        @functools.wraps(callback)
        def wrapper(*args, **kwargs):
            request.db = databases
            return callback(*args, **kwargs)
        return wrapper
    db_plugin.name = 'databases'
    return db_plugin


def pre_stop(app):
    logging.info('Disconnecting from databases')
    conns = app.config['database.connections']
    for conn in conns.values():
        conn.close()
