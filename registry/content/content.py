# -*- coding: utf-8 -*-
"""
content.py: content

Copyright 2014-2016, Outernet Inc.
Some rights reserved.

This software is free software licensed under the terms of GPLv3. See COPYING
file that comes with the source code, or http://www.gnu.org/licenses/gpl.txt.
"""


from .filters import to_filters
from ..utils.databases import row_to_dict


COLS = (
    'id', 'path', 'size', 'uploaded', 'modified', 'category', 'expiration',
    'serve_path', 'alive'
)


def process_content_data(data):
    return strip_extra(data, COLS)


def strip_extra(data, valid_keys):
    stripped_data = {}
    for key in data.keys():
        if key in valid_keys:
            stripped_data[key] = data[key]
    return stripped_data


@to_filters
def get_content(db, filters):
    query = db.Select(sets='content', what='*')
    params = []
    for filt in filters:
        query, params = filt.apply(query, params)
    db.execute(query, params)
    return [row_to_dict(row) for row in db.results]


def add_content(db, data):
    data = process_content_data(data)
    query = db.Insert('content', cols=data.keys())
    db.execute(query, data)
    db.execute('SELECT last_insert_rowid() as last_id;')
    return db.result['last_id']


def update_content(db, data):
    data = process_content_data(data)
    placeholders = {key: ':{}'.format(key) for key in data.keys()}
    query = db.Update('content', where='id=:id', **placeholders)
    db.execute(query, data)
