#!/usr/bin/python3

import argparse
import flask
import subprocess
import os
from functools import wraps

import ldaptools
import messagetools

from sqlalchemy import Column, Integer, String, Boolean, or_, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
import sqlalchemy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.expression import func


HOST = "icinga.atlantishq.de"
SIGNAL_USER_FILE = "signal_targets.txt"
app = flask.Flask("Signal Notification Gateway")
db = SQLAlchemy(app)

class Status(db.Model):

    __tablename__ = "dispatch_queue"

    service     = Column(String, primary_key=True)
    timestamp   = Column(Integer, primary_key=True)
    status      = Column(String)
    info_text   = Column(String)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = flask.request.authorization
        if not auth or not auth.password == app.config["PASSWORD"]:
            return (flask.jsonify({ 'message' : 'Authentication required' }), 401)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/smart-send', methods=["POST"])
#@login_required
def smart_send_to_clients():
    '''Send to clients based on querying the LDAP
        requests MAY include:
            - list of usernames under key "users"
            - list of groups    under key "groups"
            - neither of the above to automatically target the configured administrators group"
        retuest MUST include:
            - message as STRING in field "msg"
            OR
            - supported struct of type "ICINGA|ZABBIX|GENERIC" (see docs) in field "data"
    '''

    instructions = flask.request.json

    users = instructions.get("users")
    groups = instructions.get("groups")
    message = instructions.get("msg")

    struct = instructions.get("data")
    if struct:
        try:
            message = messagetools.load_struct(struct)
        except messagetools.UnsupportedStruct as e:
            return (408, e.response())


    persons = ldaptools.select_targets(users, groups, app.config["LDAP_ARGS"])
    save_in_dispatch_queue(persons, message)
    return (200, "OK")

def save_in_dispatch_queue(persons, message):
    pass

def create_app():

    app.config["PASSWORD"] = os.environ["SIGNAL_API_PASS"]
    app.config["SIGNAL_CLI_BIN"] = os.environ["SIGNAL_CLI_BIN"]

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Simple Telegram Notification Interface',
                        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--interface', default="localhost", help='Interface on which to listen')
    parser.add_argument('--port', default="5000", help='Port on which to listen')
    parser.add_argument("--signal-cli-bin", default=None, type=str,
                            help="Path to signal-cli binary if no in $PATH")

    parser.add_argument('--ldap-server')
    parser.add_argument('--ldap-base-dn')
    parser.add_argument('--ldap-manager-dn')
    parser.add_argument('--ldap-manager-password')

    args = parser.parse_args()

    # define ldap args #
    ldap_args = {
        "LDAP_SERVER" : args.ldap_server,
        "LDAP_BIND_DN" : args.ldap_manager_dn,
        "LDAP_BIND_PW" : args.ldap_manager_password,
        "LDAP_BASE_DN" : args.ldap_base_dn,
    }
    
    if not any([value is None for value in ldap_args.values()]):
        app.config["LDAP_ARGS"] = ldap_args
    else:
        app.config["LDAP_ARGS"] = None

    with app.app_context():
        create_app()

    app.run(host=args.interface, port=args.port, debug=True)
