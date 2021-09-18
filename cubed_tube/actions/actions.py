"""
actions.py - Admin/Creator Forms and Actions
"""

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os.path
import re
import subprocess
import time
from typing import List, Dict, Any, Optional, cast, Generator
import uuid
import yaml

from cubed_tube.actions import functions
from cubed_tube.backend import memcached_client as cache
from cubed_tube.lib.schemas import Action, ActionRecord, ActionLog, ActionStep
from cubed_tube.lib import util


def get_channels(user_hash: str) -> List[str]:
    """Returns an authorized list of channels for a given user_hash"""
    creds = util.load_credentials(ttl=30)
    config = util.load_config(ttl=30)

    if creds.roles.is_admin(user_hash):
        return config.get_channels()
    if not creds.roles.is_creator(user_hash):
        return []
    return list(creds.roles.creator[user_hash])


def get_actions(ttl: int = 0) -> List[Action]:
    """Returns action definitions loaded from disk (typings workaround)."""
    return _get_actions(ttl=ttl)


@util.cache_func
def _get_actions() -> List[Action]:
    """Returns action definitions loaded from disk."""
    with open(os.path.join(os.path.dirname(__file__), 'actions.yaml')) as fp:
        default_actions = yaml.safe_load(fp)
    actions = [Action.from_dict(a) for a in default_actions['actions']]
    try:
        with open('actions.yaml') as fp:
            custom_actions = yaml.safe_load(fp)
    except OSError:
        pass
    else:
        actions.extend(Action.from_dict(a) for a in custom_actions['actions'])
    all_functions = dir(functions)
    missing = set()
    for action in actions:
        for step in action.actions:
            if step.function is None or step.function in all_functions:
                continue
            missing.add(step.function)
    if missing:
        raise ValueError(f'Unrecognized functions: {list(missing)}')
    return actions


def get_user_actions(user_hash: str) -> List[Action]:
    """Materializes action definitions for a particular user."""
    # ensure cache is up:
    cache.create_client()

    config = util.load_config(ttl=30)
    creds = util.load_credentials(ttl=30)
    actions = []
    _is_admin = creds.roles.is_admin(user_hash)
    _is_creator = creds.roles.is_creator(user_hash)
    if not _is_admin and not _is_creator:
        return actions
    for action in get_actions(ttl=30):
        if action.group not in ['ADMIN', 'CREATOR']:
            raise ValueError(f'Unrecognized group: {action.group}')
        if action.group == 'ADMIN' and not _is_admin:
            continue
        if action.group == 'CREATOR':
            # CREATOR is checked above
            pass
        new_action = Action.from_dict({
            'name': action.name,
            'id': action.id,
            'form': deepcopy(action.form.as_dict()),
            'listed': action.listed,
        })
        for field in new_action.form.fields:
            if field.enum_class:
                if field.enum_class == 'CHANNELS':
                    field.enum = get_channels(user_hash)
                elif field.enum_class == 'SERIES':
                    field.enum = config.get_series()
                else:
                    raise ValueError(
                        f'Unrecongized enum_class: {field.enum_class}')
        actions.append(new_action)
    return actions


def validate_action(user_hash: str, action_id: str, params: Dict[str, str]
        ) -> Dict[str, str]:
    """Validates a submittted action, returning a mapping of parameters."""
    util.load_credentials(ttl=-1)  # force refresh
    all_actions = get_user_actions(user_hash)
    for action in all_actions:
        if action.id == action_id:
            break
    else:
        raise ValueError(f'{action_id} not found')
    context = {}
    for field in action.form.fields:
        if field.text:
            continue
        key = field.id
        val = params.get(key)
        if val is None:
            raise ValueError(f'{key} - required')
        if field.enum is not None and val not in field.enum:
            raise ValueError(f'{key} - invalid value')
        if field.regex and not re.match(field.regex, val):
            raise ValueError(f'{key} - invalid value')
        context[key] = val
    return context


def enqueue_action_request(
        user_hash: str, action: str, params: dict[str: str]) -> ActionRecord:
    request = ActionRecord(
        id=str(uuid.uuid4()),
        user=user_hash,
        action=action,
        params=validate_action(user_hash, action, params)
    )
    cache.ACTIONS_QUEUE.push(request)
    return request


def dequeue_action_request() -> Optional[ActionRecord]:
    action = cache.ACTIONS_QUEUE.pop()
    if not action:
        return
    return ActionRecord.from_dict(json.loads(action))


def perform_action(action: ActionRecord):
    log = cache.ActionLogger(action.id)
    cache.ACTION_LIST.push(action)

    actions = {a.id: a for a in get_actions(30)}

    try:
        if action.action not in actions:
            raise ValueError(f'action not found: {action.action}')
        action_schema = actions[action.action]
        for i, step in enumerate(action_schema.actions):
            step = cast(ActionStep, step)  # typing fix
            step_name = ', '.join(step.as_dict().keys())
            if step.run_command:
                log.heading(f'Running step {i}: {step.run_command[0]}')
                run_command(log, step, action.params)
            if step.function:
                log.heading(f'Running step {i}: {step.function}')
                kwargs = {
                    'params': action.params,
                    'action': action,
                    'log': log,
                }
                if step.kwargs:
                    kwargs.update(step.kwargs)
                getattr(functions, step.function)(**kwargs)
    except Exception as e:
        log.pre_text(str(e))
    finally:
        log.tombstone()


def run_command(log: cache.ActionLogger, step: ActionStep, params: Dict):
        command = []
        for part in step.run_command:
            if '{' in part:
                part = part.format(**params)
            command.append(part)
        log.text(f'Running command: {json.dumps(command)}')
        process = subprocess.run(command, capture_output=True, timeout=60, shell=True)
        log.text(f'Return code: {process.returncode}')
        if process.stdout:
            log.html(f'<br /><strong>stdout:<strong>')
            log.text(process.stdout.decode('utf-8'))
        if process.stderr:
            log.html(f'<br /><strong>stderr:<strong>')
            log.text(process.stderr.decode('utf-8'))


def _all_action_records() -> Generator[ActionRecord, None, None]:
    for action in cache.ACTION_LIST.get():
        try:
            yield ActionRecord.from_dict(json.loads(action))
        except Exception as e:
            print(action)
            raise


def list_action_records(user_hash) -> Generator[ActionRecord, None, None]:
    creds = util.load_credentials()
    is_admin = creds.roles.is_admin(user_hash)
    for action in _all_action_records():
        if is_admin or action.user == user_hash:
            yield action


def find_action_record(user_hash, action_id) -> Optional[ActionRecord]:
    for action in list_action_records(user_hash):
        if action.id == action_id:
            return action
    return None
