# -*- coding: utf-8 -*-
"""
utils.py: utility methods for auth

Copyright 2014-2016, Outernet Inc.
Some rights reserved.

This software is free software licensed under the terms of GPLv3. See COPYING
file that comes with the source code, or http://www.gnu.org/licenses/gpl.txt.
"""

from __future__ import unicode_literals

import functools

from bottle import request, abort

from .sessions import SessionManager


def get_session_manager():
    db = request.db.registry
    return SessionManager(db)


def check_auth(func):
    @functools.wraps(func)
    def decorator(*args, **kwargs):
        token = request.params.get('session_token')
        sessions = get_session_manager()
        verified, session = sessions.verify_session(token)
        if verified:
            request.session = session
            return func(*args, **kwargs)
        else:
            raise abort(401, session)
    return decorator
