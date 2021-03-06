# -*- coding: utf-8 -*-
"""
manager.py: content manager

Copyright 2014-2016, Outernet Inc.
Some rights reserved.

This software is free software licensed under the terms of GPLv3. See COPYING
file that comes with the source code, or http://www.gnu.org/licenses/gpl.txt.
"""

from __future__ import unicode_literals


import re
import os
import time
import pprint
import logging

from ..utils.databases import row_to_dict
from .content import add_content, get_content, update_content


class ContentException(Exception):
    pass


class ContentManager(object):
    """
    This class provides methods to query content database for their properties
    and methods to add, modify, delete those entries
    """

    DEFAULT_LIST_COUNT = 100
    MAX_LIST_COUNT = 1000

    VALID_FILTERS = ('id', 'path', 'since', 'count', 'category', 'alive',
                     'aired', 'serve_path')
    MODIFY_TRIGGERS = ('path', 'size', 'category', 'expiration',
                       'serve_path', 'alive')

    def __init__(self, config, db):
        self.root_path = os.path.abspath(config['registry.root_path'])
        self.db = db

    def exists(self, **kwargs):
        """
        Returns true if there exists atleast one content entry which is active
        and satisfies the conditions specified by the keyword arguments.
        """
        filters = kwargs
        filters['alive'] = True
        content = self.get_file(**filters)
        return bool(content)

    def get_file(self, **kwargs):
        """
        Returns the first file entry which satisfies the conditions
        specified by the keyword arguments or None
        """
        filters = kwargs
        filters['count'] = 1
        self.validate_filters(filters)
        files = get_content(self.db, **filters)
        if files:
            return self._process_entry(files[0])

    def list_files(self, **kwargs):
        """
        Returns a list of files which satisfy the conditions specified.
        The list may be truncated to specific length if the number of files
        are too large
        """
        filters = self.default_filters()
        filters.update(kwargs or {})
        filters = self.validate_list_filters(filters)
        return map(self._process_entry,
                   get_content(self.db, **filters))

    def add_file(self, client, path, params):
        """
        Adds a new file entry. A `ContentException` is raised if the entry
        conflicts with an existing entry or if `params` do not contain valid
        data. On successful addition, the new file entry is returned.
        """
        serve_path = params['serve_path']
        if self.exists(serve_path=serve_path):
            msg = 'File at serve_path {} already exists.'.format(serve_path)
            raise ContentException(msg)
        self._validate_params(params)
        id = self._add_file(path, params)
        self.record_action(file_id=id, client_name=client['name'],
                           action='add')
        return self.get_file(id=id)

    def update_file(self, client, id, params):
        """
        Updates a file entry with the specified `id`. A `ContentException` is
        raised if the entry conflicts with an existing entry or no entry with
        the specified `id` exists. On successful update, the updated file
        entry is returned.
        """
        if not self.exists(id=id):
            msg = 'File with id {} does not exist.'.format(id)
            raise ContentException(msg)
        self._validate_params(params)
        self._update_file(id, params)
        action_params = ', '.join(params.keys())
        self.record_action(
            file_id=id, client_name=client['name'], action='update',
            action_params=action_params)
        return self.get_file(id=id)

    def delete_file(self, client, id):
        """
        Deactivates a file entry with the specified `id`. A `ContentException`
        is raised if no such entry exists. On successful deactivation, the
        updated file entry is returned.
        """
        if not self.exists(id=id):
            msg = 'File with id {} does not exist.'.format(id)
            raise ContentException(msg)
        self._delete_file(id)
        self.record_action(
            file_id=id, client_name=client['name'], action='delete')

    def _process_entry(self, data):
        data['alive'] = bool(data['alive'])
        return data

    def validate_list_filters(self, filters):
        """
        Validates filters used for listing file entries and returns a valid
        copy of filters. Filters are specified as a dict.
        """
        filters = filters.copy()
        if 'serve_path' in filters or 'since' in filters:
            # Remove count filter if `path` or `since` filter are applicable
            try:
                del filters['count']
            except KeyError:
                pass
        # Ensure we return a maximum of `MAX_LIST_COUNT` entries
        if 'count' in filters:
            filters['count'] = min(filters['count'], self.MAX_LIST_COUNT)
        # Ensure serve_path is a valid regex
        if 'serve_path' in filters:
            try:
                re.compile(filters['serve_path'])
            except re.error:
                raise ValueError(
                    'Invalid regular expression for serve_path: {}'.format(
                        filters['serve_path']))
        return filters

    def default_filters(self):
        return {'count': self.DEFAULT_LIST_COUNT}

    def _add_file(self, path, data):
        data['alive'] = True
        data['uploaded'] = data['modified'] = time.time()
        data['size'] = os.path.getsize(path)
        logging.info('Adding new file {} with data: {}'.format(
            path, pprint.pformat(data)))
        return add_content(self.db, data)

    def _validate_params(self, params):
        if 'path' in params:
            self._validate_path(params.get('path'))

    def _validate_path(self, path):
        if not path:
            raise ContentException('Invalid path {}'.format(path))
        if not path.startswith(self.root_path):
            msg = ' {} does not fall under {} hierarchy.'.format(
                path, self.root_path)
            raise ContentException(msg)
        if not os.path.isfile(path):
            msg = 'No file at path {}'.format(path)
            raise ContentException(msg)

    def _update_file(self, id, data):
        data['id'] = id
        if 'path' in data:
            path = data.get('path')
            data['size'] = os.path.getsize(path)
        for key in self.MODIFY_TRIGGERS:
            if key in data:
                data['modified'] = time.time()
                break
        logging.info('Updating file with id {} with data: \n{}'.format(
            id, pprint.pformat(data)))
        update_content(self.db, data)

    def _delete_file(self, id):
        data = {}
        data['id'] = id
        data['alive'] = False
        data['modified'] = time.time()
        logging.info('Setting file with id {} to dead'.format(id))
        update_content(self.db, data)

    def record_action(self, file_id, client_name, action, action_params='',
                      timestamp=None):
        timestamp = timestamp or time.time()
        records = ActionRecords(self.db)
        records.add_action(
            file_id, client_name, action, action_params, timestamp)

    def validate_filters(self, filters):
        for key in filters.keys():
            if key not in self.VALID_FILTERS:
                raise ContentException('Invalid filter: {}'.format(key))

    def split_valid_filters(self, filters):
        valid = {}
        invalid = {}
        for key, value in filters.items():
            if key in self.VALID_FILTERS:
                valid[key] = value
            else:
                invalid[key] = value
        return valid, invalid


class ActionRecords(object):

    TABLE = 'history'

    def __init__(self, db):
        self.db = db

    def get_actions(self, file_id):
        query = self.db.Select('*', sets=self.TABLE, where='file_id = ?')
        self.db.execute(query, (file_id,))
        return [row_to_dict(row) for row in self.db.results]

    def add_action(self, file_id, client_name, action, action_params,
                   timestamp):
        action_data = {
            'file_id': file_id,
            'client_name': client_name,
            'action': action,
            'action_params': action_params,
            'timestamp': timestamp,
        }
        query = self.db.Insert(self.TABLE, cols=action_data.keys())
        self.db.execute(query, action_data)

    def clear_actions(self, file_id):
        query = self.db.Delete(self.TABLE, where='file_id = ?')
        self.db.execute(query, (file_id,))
