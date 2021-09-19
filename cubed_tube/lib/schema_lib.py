"""
schema_lib - The base class for all schema objects

It looks like this may be duplicative to pydantic (and be surely lesser). But
I made this! ::cry::

TODO: Evaluate pydantic for replacing this whole module.
"""


from copy import deepcopy
from dataclasses import is_dataclass, asdict, fields, MISSING, Field
from typing import Optional, Union, Any, Dict, get_origin, get_args

class MissingFieldError(ValueError):
    pass

def has_dataclass(type_: Any):
    return (
        is_dataclass(type_)
        or any(has_dataclass(t) for t in get_args(type_))
    )

class Schema:
    """
    Recursively build out a dataclass.
    
    Has support for list, dict, and Optional.
    """
    @classmethod
    def from_dict(cls, data: Dict, _path='$'):
        if not(is_dataclass(cls)):
            raise ValueError("schemas objects must be decorated as dataclasses")
        if data is None:
            data = {}
        data = deepcopy(data)
        unknowns = set(data.keys()) - set(cls.__annotations__.keys())
        if unknowns:
            raise ValueError(
                f"[{_path}/{cls.__name__}] Unrecognized fields: {str(unknowns)}"
            )
        for field in fields(cls):
            name = field.name
            try:
                data[name] = cls._check_type(
                    field.type, data.get(name), f'{_path}.{name}')
            except MissingFieldError as e:
                data[name] = cls._get_default(field)
                if data[name] is None:
                    raise ValueError(e.args[0])
            else:
                if data[name] is None:
                    data[name] = cls._get_default(field)

        return cls(**data)

    @classmethod
    def _get_default(cls, field: Field):
        if field.default is not MISSING:
            return field.default
        elif field.default_factory is not MISSING:
            return field.default_factory()
        else:
            return None


    @classmethod
    def _check_type(cls, type_: Any, value: Any, _path: str):
        field_args = get_args(type_)
        # Optional[Foo] or Union[Foo, Bar]
        if get_origin(type_) is Union:
            if has_dataclass(type_) and not all(
                    has_dataclass(t) or t is type(None) for t in field_args):
                raise ValueError(
                    f'{_path}: schemas Unions do not support mixed types')
            for sub_type in field_args:
                exceptions = []
                try:
                    return cls._check_type(sub_type, value, _path)
                except Exception as e:
                    exceptions.append(e)
            if len(exceptions == 1):
                raise exceptions[0]
            raise ValueError(exceptions)

        if is_dataclass(type_):
            return type_.from_dict(value)

        if value is None:
            if type_ is type(None):
                return None
            raise MissingFieldError(f'{_path}: Received None')

        # foo: List[Foo]
        if get_origin(type_) is list:
            return [
                cls._check_type(field_args[0], item, f'{_path}[{i}]') 
                for i, item in enumerate(value)
            ]

        # foo: Dict[str, Foo]
        if get_origin(type_) is dict and is_dataclass(field_args[1]):
            return {
                key: cls._check_type(field_args[1], val, f'{_path}.{key}')
                for key, val in value.items()
            }
        
        return value

    def as_dict(self, allow_none=False) -> Dict:
        def _dict_factory(items):
            final = {}
            for k, v in items:
                if not allow_none and v is None:
                    continue
                final[k] = self._serialize_value(v, allow_none=allow_none)
            return final
        return asdict(self, dict_factory=_dict_factory)


    def _serialize_value(self, value, allow_none=False):
        if isinstance(value, Schema):
            return value.as_dict(allow_none=allow_none)
        if isinstance(value, list):
            return [self._serialize_value(v, allow_none=allow_none)
                    for v in value]
        if isinstance(value, dict):
            return {k: self._serialize_value(v, allow_none=allow_none)
                    for k, v in value.items()}
        return value

