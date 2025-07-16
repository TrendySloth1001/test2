import MySQLdb

DB_CONFIG = {
    'host': 'test.schooldesk.org',
    'user': 'ANSK',
    'passwd': 'Nick8956',
    'db': 'devhub'
}

def get_db_connection():
    return MySQLdb.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        passwd=DB_CONFIG['passwd'],
        db=DB_CONFIG['db']
    ) 