import os
from datetime import datetime, date, timedelta
import hashlib
import psycopg2

from pgcopy import util

from nose.plugins.skip import SkipTest

db_state = {
        'connection_params': {
            'dbname': os.getenv('POSTGRES_DB', 'pgcopy_test'),
            'host': os.getenv('POSTGRES_HOST'),
            'user': os.getenv('POSTGRES_USER'),
            'password': os.getenv('POSTGRES_PASSWORD'),
        },
        'conn': None,
        'drop': False,
    }

def get_conn():
    conn = db_state.get('conn')
    if conn is None:
        conn = create_db()
        db_state['conn'] = conn
    return conn

def create_db():
    "connect to test db"
    try:
        return psycopg2.connect(**db_state['connection_params'])
    except psycopg2.OperationalError as exc:
        nosuch_db = 'database "%s" does not exist' % db_state['connection_params']['dbname']
        if nosuch_db in str(exc):
            try:
                master = psycopg2.connect(database='postgres')
                master.rollback()
                master.autocommit = True
                cursor = master.cursor()
                cursor.execute('CREATE DATABASE %s' % db_state['connection_params']['dbname'])
                cursor.close()
                master.close()
            except psycopg2.Error as exc:
                message = ('Unable to connect to or create test db '
                            + db_state['connection_params']['dbname']
                            + '.\nThe error is: %s' % exc)
                raise RuntimeError(message)
            else:
                conn = psycopg2.connect(**db_state['connection_params'])
                db_state['drop'] = True
                return conn

def drop_db():
    "Drop test db"
    if not db_state['drop']:
        return
    get_conn().close()
    master = psycopg2.connect(database='postgres')
    master.rollback()
    master.autocommit = True
    cursor = master.cursor()
    cursor.execute('DROP DATABASE %s' % db_state['connection_params']['dbname'])
    cursor.close()
    master.close()

genbool = lambda i: 0 == (i % 3)
genint = lambda i: i
genfloat = lambda i: 1.125 * i
gendate = lambda i: date(1708, 1, 1) + timedelta(i % (250 * 365))
gendatetime = lambda i: datetime(1970, 1, 1) + timedelta(hours=i)
gendatetimetz = lambda i: util.to_utc(datetime(1970, 1, 1) + timedelta(hours=i))
genstr12 = lambda i: hashlib.md5(str(i).encode()).hexdigest()[:12 - (i % 3)].encode()

datagen = {
        'bool': genbool,
        'smallint': genint,
        'integer': genint,
        'bigint': genint,
        'real': genfloat,
        'double precision': genfloat,
        'date': gendate,
        'timestamp': gendatetime,
        'timestamp with time zone': gendatetimetz,
        'varchar(12)': genstr12,
        'char(12)': genstr12,
    }

colname = lambda i: chr(ord('a') + i)

class TemporaryTable(object):
    temp = 'TEMPORARY'
    null = 'NOT NULL'
    data = None
    record_count = 0

    def temp_schema_name(self):
        cursor = self.conn.cursor()
        cursor.execute("""SELECT nspname
                          FROM   pg_namespace
                          WHERE  oid = pg_my_temp_schema()""")
        return cursor.fetchall()[0][0]

    def setUp(self):
        self.conn = get_conn()
        self.conn.rollback()
        self.conn.autocommit = False
        self.cur = self.conn.cursor()
        self.table = self.__class__.__name__.lower()
        colsql = []
        for i, coltype in enumerate(self.datatypes):
            colsql.append('%s %s %s' % (colname(i), coltype, self.null))
        try:
            collist = ', '.join(colsql)
            cmd = "CREATE {} TABLE {} ({})"
            self.cur.execute(cmd.format(self.temp, self.table, collist))
        except psycopg2.ProgrammingError as e:
            self.conn.rollback()
            if '42704' == e.pgcode:
                raise SkipTest('Unsupported datatype')

        schema = self.temp_schema_name()
        self.schema_table = '{}.{}'.format(schema, self.table)

        self.cols = [colname(i) for i in range(len(self.datatypes))]
        if self.data is None and self.record_count > 0:
            self.data = self.generate_data(self.record_count)

    def generate_data(self, count):
        data = []
        gen = [datagen[t] for t in self.datatypes]
        for i in range(count):
            row = [g(i) for g in gen]
            data.append(tuple(row))
        return data

    def tearDown(self):
        self.conn.rollback()
