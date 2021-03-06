# -*- coding: utf-8 -*-
"""
api.py: api module

Copyright 2014-2016, Outernet Inc.
Some rights reserved.

This software is free software licensed under the terms of GPLv3. See COPYING
file that comes with the source code, or http://www.gnu.org/licenses/gpl.txt.
"""

from __future__ import unicode_literals

import os
import logging

from bottle import request, abort, static_file, HTTP_CODES

from ..utils.http import urldecode_params
from .manager import ContentManager, ContentException
from ..auth.utils import check_auth


ADD_FILE_REQ_PARAMS = ('path', 'serve_path')


def get_manager():
    config = request.app.config
    db = request.db.registry
    return ContentManager(config=config, db=db)


def check_params(params, required_params):
    for p in required_params:
        val = params.get(p, None)
        if not val:
            abort(400, '`{}` must be specified'.format(p))


@check_auth
def list_files():
    content_mgr = get_manager()
    params = urldecode_params(request.query)
    valid_params, _ = content_mgr.split_valid_filters(params)
    try:
        files = content_mgr.list_files(**valid_params)
        return {'success': True, 'results': files, 'count': len(files)}
    except (ContentException, ValueError) as exc:
        return {'success': False, 'error': str(exc)}
    except Exception as exc:
        logging.exception('Error while adding file: {}'.format(exc))
        return {'success': False, 'error': 'Unknown Error'}


def get_file(id):
    config = request.app.config
    item = get_manager().get_file(id=id)
    if item:
        path = item['path']
        root_dir = config['registry.root_path']
        rel_path = os.path.relpath(path, root_dir)
        return static_file(rel_path, root=root_dir,
                           download=os.path.basename(path))
    else:
        raise abort(404, HTTP_CODES[404])


@check_auth
def add_file():
    params = urldecode_params(request.forms)
    check_params(params, ADD_FILE_REQ_PARAMS)
    path = params.get('path')
    client = request.session['client']
    content_mgr = get_manager()
    try:
        result = content_mgr.add_file(client, path, params)
        return {'success': True, 'results': [result]}
    except ContentException as exc:
        return {'success': False, 'error': str(exc)}
    except Exception as exc:
        logging.exception('Error while adding file: {}'.format(str(exc)))
        return {'success': False, 'error': 'Unknown Error'}


@check_auth
def update_file(id):
    params = urldecode_params(request.forms)
    client = request.session['client']
    content_mgr = get_manager()
    try:
        result = content_mgr.update_file(client, id, params)
        return {'success': True, 'results': [result]}
    except ContentException as exc:
        return {'success': False, 'error': str(exc)}
    except Exception as exc:
        logging.exception('Error while updating file: {}'.format(str(exc)))
        return {'success': False, 'error': 'Unknown Error'}


@check_auth
def delete_file(id):
    client = request.session['client']
    content_mgr = get_manager()
    try:
        content_mgr.delete_file(client, id)
        return {'success': True}
    except ContentException as exc:
        return {'success': False, 'error': str(exc)}
    except Exception as exc:
        logging.exception('Error while deleting file: {}'.format(str(exc)))
        return {'success': False, 'error': 'Unknown Error'}
