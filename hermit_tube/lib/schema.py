from dataclasses import dataclass, is_dataclass, asdict, fields, MISSING
from typing import Optional, Union, Any, get_origin, get_args

class Schema:
    """
    Recursively build out a dataclass.
    
    Has support for list, dict, and Optional.
    """
    @classmethod
    def from_dict(cls, **kwargs):
        unknowns = set(kwargs.keys()) - set(cls.__annotations__.keys())
        if unknowns:
            raise ValueError("Unrecognized fields: " + str(unknowns))
        for field in fields(cls):
            name = field.name
            field_args = get_args(field.type)
            # foo: Optional[Foo] (which is really Union[Foo, None])
            is_optional = (get_origin(field.type) is Union 
                           and type(None) in field_args)
            if is_optional and name not in kwargs:
                if field.default is not MISSING:
                    kwargs[name] = field.default
                elif field.default_factory is not MISSING:
                    kwargs[name] = field.default_factory()
                else:
                    kwargs[name] = None
                continue

            if name not in kwargs:
                continue

            if is_optional and is_dataclass(field_args[0]):
                kwargs[name] = field_args[0].from_dict(**kwargs[name])

            # foo: Foo
            if is_dataclass(field.type):
                kwargs[name] = field.type.from_dict(**kwargs[name])

            # foo: list[Foo]
            if get_origin(field.type) is list and is_dataclass(field_args[0]):
                kwargs[name] = [
                    field_args[0].from_dict(**item) for item in kwargs[name]
                ]

            # foo: dict[str, Foo]
            if get_origin(field.type) is dict and is_dataclass(field_args[1]):
                kwargs[name] = {
                    key: field_args[1].from_dict(**val)
                    for key, val in kwargs[name].items()
                }

        return cls(**kwargs)

    def as_dict(self, allow_none=False):
        return asdict(self, dict_factory=lambda items: {
            k: v for k, v in items if allow_none or v is not None
        })


@dataclass
class PlaylistChannel(Schema):
    name: str
    playlist: Optional[str]
    channel: Optional[str]
    videos: Optional[list[str]]
    type: Optional[str] = 'youtube'
    record: Optional[Any] = None

@dataclass
class PlaylistSeries(Schema):
    title: str
    slug: str
    channels: list[PlaylistChannel]
    start: Optional[int]
    ignore_video_ids: Optional[list[str]]
    default: bool = False
    active: bool = True
    record: Optional[Any] = None

@dataclass
class Playlist(Schema):
    title: str
    version: str
    series: list[PlaylistSeries]

@dataclass
class ConfigMemcache(Schema):
    host: str
    write_frequency: Optional[int]

@dataclass
class ConfigBackend(Schema):
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    SECRET_KEY: str
    cors_origins: list[str]
    domain: str
    user_salt: Optional[str]
    memcache: Optional[ConfigMemcache]

@dataclass
class ConfigCloud(Schema):
    name: str
    url: str
    access_key: str
    secret: str

@dataclass
class ConfigScraper(Schema):
    yt_api_key: str

@dataclass
class Credentials(Schema):
    scraper: ConfigScraper
    backend: Optional[ConfigBackend]
    cloud_storage: Optional[ConfigCloud]
