
from copy import deepcopy
from dataclasses import dataclass, is_dataclass, asdict, fields, MISSING, Field
from typing import Optional, Union, Any, get_origin, get_args

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
    def from_dict(cls, data: dict, _path='$'):
        if not(is_dataclass(cls)):
            raise ValueError("Schema objects must be decorated as dataclasses")
        data = deepcopy(data)
        unknowns = set(data.keys()) - set(cls.__annotations__.keys())
        if unknowns:
            raise ValueError("Unrecognized fields: " + str(unknowns))
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
                    f'{_path}: Schema Unions do not support mixed types')
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

        # foo: list[Foo]
        if get_origin(type_) is list:
            return [
                cls._check_type(field_args[0], item, f'{_path}[{i}]') 
                for i, item in enumerate(value)
            ]

        # foo: dict[str, Foo]
        if get_origin(type_) is dict and is_dataclass(field_args[1]):
            return {
                key: cls._check_type(field_args[1], val, f'{_path}.{key}')
                for key, val in value.items()
            }
        
        return value

    def as_dict(self, allow_none=False):
        return asdict(self, dict_factory=lambda items: {
            k: v for k, v in items if allow_none or v is not None
        })


@dataclass
class ConfigChannel(Schema):
    name: str
    playlist: Optional[str]
    channel: Optional[str]
    videos: Optional[list[str]]
    type: Optional[str] = 'youtube'
    record: Optional[Any] = None

@dataclass
class ConfigSeries(Schema):
    title: str
    slug: str
    channels: list[ConfigChannel]
    start: Optional[int]
    ignore_video_ids: Optional[list[str]]
    default: bool = False
    active: bool = True
    record: Optional[Any] = None

@dataclass
class ConfigLink(Schema):
    text: str
    href: str

@dataclass
class ConfigLinkList(Schema):
    text: str
    links: list[ConfigLink]

@dataclass
class ConfigSite(Schema):
    menu_links: Optional[list[Union[ConfigLink, ConfigLinkList]]]
    header: Optional[str]

@dataclass
class Configuration(Schema):
    title: str
    series: list[ConfigSeries]
    site: Optional[ConfigSite]
    version: str = ''

@dataclass
class CredMemcache(Schema):
    host: str
    write_frequency: Optional[int]

@dataclass
class CredBackend(Schema):
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    SECRET_KEY: str
    cors_origins: list[str]
    domain: str
    user_salt: Optional[str]
    memcache: Optional[CredMemcache]
    worker_port: Optional[int]

@dataclass
class CredCloud(Schema):
    name: str
    url: str
    access_key: str
    secret: str

@dataclass
class CredScraper(Schema):
    yt_api_key: str

@dataclass
class Credentials(Schema):
    site_name: str
    scraper: CredScraper
    backend: Optional[CredBackend]
    cloud_storage: Optional[CredCloud]
