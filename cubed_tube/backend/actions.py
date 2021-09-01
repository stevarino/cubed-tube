"""
actions.py - Admin/Creator Forms and Actions
"""

from copy import deepcopy
import re
from typing import List
from cubed_tube.lib import util, schema

config: schema.Configuration = util.load_config()

ADMIN = ('acl', 'admin')
CREATOR = ('acl', 'creator')

CHANNELS = ('validator', 'channels')
SERIES = ('validator', 'series')


ACTIONS = [
    {
        'name': 'Deploy Cubed Tube Version',
        'id': 'deploy',
        'group': ADMIN,
        'form': {
            'fields': [
                {
                    'id': 'version',
                    'regex': '^[0-9.a-z]+$',
                },
            ],
        },
        'actions': [
            {'run_command': ['pip', 'install', 'cubedtube={version}']},
        ]
    },
    {
        'name': 'Restart Workers',
        'id': 'restart',
        'group': ADMIN,
        'form': {
            'fields': [],
        },
        'actions': [
            {'run_command': ['scripts/restart.sh']}
        ]
    },
    {
        'name': 'Add Video',
        'id': 'add_video',
        'group': CREATOR,
        'form': {
            'fields': [
                {
                    'id': 'series',
                    'enum': SERIES,
                },
                {
                    'id': 'channel',
                    'enum': CHANNELS,
                },
                {
                    'id': 'video_id',
                    'regex': '^[0-9.a-z]+$',
                },
            ]
        }
    },
]


def user_is_known(user_hash: str) -> bool:
    return is_admin(user_hash) or is_creator(user_hash)


def is_admin(user_hash: str) -> bool:
    creds: schema.Credentials = util.load_credentials(ttl=30)
    return bool(creds.roles and creds.roles.admin and 
                user_hash in creds.roles.admin)


def is_creator(user_hash: str) -> bool:
    creds: schema.Credentials = util.load_credentials(ttl=30)
    return creds.roles and ((
        creds.roles.creator and user_hash in creds.roles.creator
    ) or (
        creds.roles.admin and user_hash in creds.roles.admin
    ))


def get_channels(user_hash: str) -> List[str]:
    """Returns an authorized list of channels for a given user_hash"""
    creds: schema.Credentials = util.load_credentials(ttl=30)
    config: schema.Configuration = util.load_config(ttl=30)
    if is_admin(user_hash):
        return config.get_channels()
    if not is_creator(user_hash):
        return []
    return list(creds.roles.creator.values())


def get_user_actions(user_hash: str):
    config: schema.Configuration = util.load_config(ttl=30)
    actions = []
    _is_admin = is_admin(user_hash)
    _is_creator = is_creator(user_hash)
    if not _is_admin and not _is_creator:
        return actions
    for action in ACTIONS:
        if action['group'] is ADMIN and not _is_admin:
            continue
        if action['group'] is CREATOR and not _is_creator:
            continue
        new_action = {k: deepcopy(action[k]) for k in action 
                      if k in ['name', 'id', 'form']}
        for field in new_action['form']['fields']:
            if field.get('enum'):
                if field['enum'] is CHANNELS:
                    field['enum'] = get_channels(user_hash)
                if field['enum'] is SERIES:
                    field['enum'] = config.get_series()
        actions.append(new_action)
    return actions


def parse_action(user_hash, form_data: dict[str: str]):
    util.load_credentials(ttl=-1)  # force refresh
    all_actions = get_user_actions(user_hash)
    for action in all_actions:
        if action['id'] == form_data.get('form'):
            break
    else:
        raise ValueError(f'{action["id"]} not found')
    context = {}
    for field in action['form']['fields']:
        key = field['id']
        val = form_data.get(key)
        if val is None:
            raise ValueError(f'{key} - required')
        if field.get('enum') and val not in field['enum']:
            raise ValueError(f'{key} - invalid value')
        if field.get('regex') and not re.match(field['regex'], val):
            raise ValueError(f'{key} - invalid value')
        context[key] = val
    return context


