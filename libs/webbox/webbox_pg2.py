


import logging, urllib2, uuid, rdflib, os, traceback, mimetypes, shutil, json
import psycopg2
from txpostgres import txpostgres
from twisted.internet.defer import Deferred
from time import strftime

## webbox to txpostgres bridge

POSTGRES_DB = "postgres" # default db fallback if db name is none
WBPREFIX = "wb_"

def connect(db_name,db_user,db_pass):
    conn = txpostgres.Connection()
    conn_str = ("dbname='{0}' user='{1}' password='{2}'".format(db_name or POSTGRES_DB, db_user, db_pass))    
    return conn.connect(conn_str)

def connect_box(box_name,db_user,db_pass):
    return connect(WBPREFIX + box_name, db_user, db_pass)

def auth(db_user,db_pass):
    d = Deferred()
    connect(None,db_user,db_pass).addCallbacks(lambda *x: d.callback(True), lambda *x: d.callback(False))
    return d

def list_databases(db_user, db_pass):
    return_d = Deferred()

    def db_list(rows):
        dbs = []
        for row in rows:
            db = row[0] # strip wb_ prefix from name
            dbs.append(db)
        return_d.callback(dbs)

    def connected(conn):
        cursor = conn.cursor()
        d = cursor.execute("SELECT datname FROM pg_database WHERE datname LIKE %s", [WBPREFIX+"%"])
        d.addCallback(lambda _: cursor.fetchall())
        d.addCallback(db_list)

    connect("postgres", db_user, db_pass).addCallback(connected)
    return return_d


def list_boxes(db_user, db_pass):
    return_d = Deferred()

    def db_list(dbs):
        boxes = []
        for db in dbs:
            box = db[len(WBPREFIX):]
            boxes.append(box)
        return_d.callback(boxes)

    d = list_databases(db_user, db_pass)
    d.addCallback(db_list)

    return return_d


def create_user(new_username, new_password, db_user, db_pass):

    return_d = Deferred()

    def created(row):
        return_d.callback(None)

    def connected(conn):
        cursor = conn.cursor()
        d = cursor.execute("CREATE ROLE %s LOGIN ENCRYPTED PASSWORD '%s' NOSUPERUSER INHERIT CREATEDB NOCREATEROLE" % (new_username, new_password))
        d.addCallback(lambda _: cursor.fetchone())
        d.addCallback(created)

    connect("postgres", db_user, db_pass).addCallback(connected)
    return return_d


def create_box(box_name, db_user, db_pass):
    db_name = WBPREFIX + box_name 
    root_conn = psycopg2.connect(dbname = POSTGRES_DB, user = db_user, password = db_pass) # have to specify a db that exists
    root_conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    root_cur = root_conn.cursor()
    root_cur.execute("CREATE DATABASE %s WITH ENCODING='UTF8' OWNER=%s CONNECTION LIMIT=-1" % (db_name, db_user))
    root_conn.commit()
    root_cur.close()
    root_conn.close()    

    # load in definition from data/objectstore.sql
    fh_objsql = open(os.path.join(os.path.dirname(__file__),"..","..","data","objectstore.sql")) # FIXME put into config
    objsql = fh_objsql.read()
    fh_objsql.close()

    root_conn = psycopg2.connect(database = db_name, user = db_user, password = db_pass) # reconnect to this new db, and without the isolation level set
    root_cur = root_conn.cursor()
    root_cur.execute(objsql)
    root_conn.commit()
    root_cur.close()
    root_conn.close()
    return

def create_role():
    
    return 

