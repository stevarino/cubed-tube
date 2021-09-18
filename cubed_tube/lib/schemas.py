
from dataclasses import dataclass, field
import time
from typing import Optional, List, Dict, Any, Union

from cubed_tube.lib.schema_lib import Schema

#############################################################################
# CONFIGURATION FILE
#############################################################################

@dataclass
class ConfigChannel(Schema):
    name: str
    playlist: Optional[str]
    channel: Optional[str]
    videos: Optional[List[str]]
    type: Optional[str] = 'youtube'
    record: Optional[Any] = None

    def get_normalized_name(self):
        """Returns a normalized channel name (lowercase, no spaces)"""
        return self.name.lower().replace(' ', '')


@dataclass
class ConfigSeries(Schema):
    title: str
    slug: str
    channels: List[ConfigChannel]
    start: Optional[int]
    ignore_video_ids: Optional[List[str]]
    default: bool = False
    active: bool = True
    record: Optional[Any] = None

    def get_channels(self):
        """Returns a list of channels in the series."""
        return [channel.get_normalized_name() for channel in self.channels]


@dataclass
class ConfigLink(Schema):
    text: str
    href: str


@dataclass
class ConfigLinkList(Schema):
    text: str
    links: List[ConfigLink]


@dataclass
class ConfigSite(Schema):
    menu_links: Optional[List[Union[ConfigLink, ConfigLinkList]]]
    header: Optional[str]


@dataclass
class Configuration(Schema):
    title: str
    series: List[ConfigSeries]
    site: Optional[ConfigSite]
    version: str = ''

    def get_channels(self) -> List[str]:
        """Returns a list of channels across all series, sorted."""
        channels = set()
        for series in self.series:
            channels.update(series.get_channels())
        return sorted(channels)

    def get_series(self) -> List[str]:
        """Returns a list of series (by slug) in order of appearance."""
        return [series.slug for series in self.series]

#############################################################################
# CREDENTIAL FILE
#############################################################################

@dataclass
class CredMemcache(Schema):
    host: Optional[str]
    write_frequency: Optional[int]
    enabled: bool = field(default=True)

    def writes_enabled(self):
        return self.host and self.write_frequency and self.enabled


@dataclass
class CredBackend(Schema):
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    SECRET_KEY: str
    cors_origins: List[str]
    domain: str
    # NOTE: user_salt should not be changed even if leaked.
    user_salt: Optional[str]
    worker_port: int = 3900
    memcache: CredMemcache = field(default_factory=CredMemcache)


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
class CredRoles(Schema):
    admin: List[str] = field(default_factory=list)
    creator: Dict[str, List[str]] = field(default_factory=dict)

    def is_admin(self, user_hash):
        return user_hash in self.admin

    def is_creator(self, user_hash):
        return user_hash in self.creator

    def is_known(self, user_hash):
        return self.is_admin(user_hash) or self.is_creator(user_hash)


@dataclass
class Credentials(Schema):
    site_name: str
    scraper: CredScraper
    backend: Optional[CredBackend]
    cloud_storage: Optional[CredCloud]
    roles: CredRoles = field(default_factory=CredRoles)


#############################################################################
# OVERRIDES FILE
#############################################################################

@dataclass
class Overrides(Schema):
    credentials: Dict[str, str] = field(default_factory=dict)
    configuration: Dict[str, str] = field(default_factory=dict)


#############################################################################
# ACTION SCHEMAS
#############################################################################

@dataclass
class ActionRecord(Schema):
    """A record of a given action by a user."""
    id: str
    user: str
    action: str
    params: Dict[str, Any]
    time: float = field(default_factory=time.time)


@dataclass
class ActionLog(Schema):
    """A log message for a given action."""
    heading: Optional[str]
    html: Optional[str]
    text: Optional[str]
    pre_text: Optional[str]
    tombstone: Optional[bool]
    time: float = field(default_factory=time.time)


@dataclass
class ActionField(Schema):
    """Used in ActionForm, represents a given form field."""
    id: Optional[str]
    regex: Optional[str]
    enum_class: Optional[str]
    enum: Optional[str]
    text: Optional[str]
    html: Optional[str]


@dataclass
class ActionForm(Schema):
    """Part of an Action defition, describes a user-fillable form."""
    fields: List[ActionField]


@dataclass
class ActionStep(Schema):
    """Part of an Action definition, describes a given step for an action."""
    run_command: Optional[List[str]]
    function: Optional[str]
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Action(Schema):
    name: str
    id: str
    group: Optional[str]
    form: ActionForm
    actions: Optional[List[ActionStep]]
    listed: bool = field(default=True)
