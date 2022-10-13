import collections
import datetime
import netrc
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlencode

import dateutil.parser
import requests
import yaml
from slugify import slugify


import logging


def logger(name=None, level=None):
    """
    A logger.
    :param name: module name
    :param level: debugging level
    :return: a logger instance.
    """

    name = name if name else __name__
    level = level if level else logging.INFO

    _logger = logging.getLogger(name)
    _logger.setLevel(level)
    _hdlr = logging.StreamHandler()
    _fmt = logging.Formatter("[%(asctime)s][%(levelname)s][%(name)s] %(message)s")
    _hdlr.setFormatter(_fmt)
    _logger.addHandler(_hdlr)

    return _logger

NETRC_MACHINE = "mixcloud-api"
API_ROOT = "https://api.mixcloud.com"
OAUTH_ROOT = "https://www.mixcloud.com/oauth"

API_ERROR_MESSAGE = "Mixcloud {} API returned HTTP code {}"

log = logger(__name__)


class MixcloudOauthError(Exception):
    pass


class APIError(Exception):
    pass


def get(*args, **kwargs):
    """A wrapper for requests.GET method"""
    response = requests.get(*args, **kwargs)
    if response.status_code == 200:
        return response
    raise APIError(API_ERROR_MESSAGE.format("GET", response.status_code))


def post(*args, **kwargs):
    """A wrapper for requests.POST method"""
    response = requests.post(*args, **kwargs)
    if response.status_code == 200:
        return response
    raise APIError(API_ERROR_MESSAGE.format("POST", response.status_code))


def setup_yaml():
    def construct_yaml_str(self, node):
        # Override the default string handling function
        # to always return unicode objects
        return self.construct_scalar(node)

    tag = "tag:yaml.org,2002:str"
    yaml.Loader.add_constructor(tag, construct_yaml_str)
    yaml.SafeLoader.add_constructor(tag, construct_yaml_str)


def get_many(url, limit=None, offset=None):
    """Gets many records from Mixcloud API"""
    params = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    r = get(url, params=params)
    return r.json()


def get_all(url):
    """A wrapper for `get_many()`: a generator getting and iterating through all results"""
    data = get_many(url, limit=50)
    yield from data["data"]
    while "paging" in data and "next" in data["paging"]:
        data = get_many(data["paging"]["next"])
        yield from data["data"]


class MixcloudOauth:
    """
    Assists in the OAuth dance with Mixcloud to get an access token.
    """

    def __init__(self, client_id=None, client_secret=None, redirect_uri=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def authorize_url(self):
        """
        Return a URL to redirect the user to for OAuth authentication.
        """
        auth_url = OAUTH_ROOT + "/authorize"
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        return "{}?{}".format(auth_url, urlencode(params))

    def exchange_token(self, code):
        """
        Exchange the authorization code for an access token.
        """
        access_token_url = OAUTH_ROOT + "/access_token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "code": code,
        }
        resp = requests.get(access_token_url, params=params)
        if not resp.ok:
            raise MixcloudOauthError("Could not get access token.")
        return resp.json()["access_token"]


class Mixcloud:
    def __init__(self, api_root=API_ROOT, access_token=None):
        self.api_root = api_root
        if access_token is None:
            try:
                # Check there is a netrc file.
                netrc_auth = netrc.netrc()
            except FileNotFoundError:
                pass
            else:
                try:
                    # Attempt netrc lookup.
                    credentials = netrc_auth.authenticators(NETRC_MACHINE)
                    if netrc_auth:
                        access_token = credentials[2]
                except netrc.NetrcParseError:
                    # Configuration errors unrelated to the Mixcloud entry
                    # will cause this exception to be thrown, whether or not
                    # there is a Mixcloud entry.
                    pass
        self.access_token = access_token

    def artist(self, key):
        url = "{}/artist/{}".format(self.api_root, key)
        r = get(url)
        return Artist.from_json(r.json())

    def user(self, key):
        url = "{}/{}".format(self.api_root, key)
        r = get(url)
        return User.from_json(r.json(), m=self)

    def me(self):
        url = "{}/me/".format(self.api_root)
        r = get(url, {"access_token": self.access_token})
        return User.from_json(r.json(), m=self)

    def upload(self, cloudcast, mp3file, picturefile=None):
        url = "{}/upload/".format(self.api_root)
        payload = {
            "name": cloudcast.name,
            "percentage_music": 100,
            "description": cloudcast.description(),
        }
        for num, sec in enumerate(cloudcast.sections()):
            payload["sections-%d-artist" % num] = sec.track.artist.name
            payload["sections-%d-song" % num] = sec.track.name
            payload["sections-%d-start_time" % num] = sec.start_time

        for num, tag in enumerate(cloudcast.tags):
            payload["tags-%s-tag" % num] = tag

        files = {"mp3": mp3file}
        if picturefile is not None:
            files["picture"] = picturefile

        r = post(
            url, data=payload, params={"access_token": self.access_token}, files=files
        )
        return r

    def upload_yml_file(self, ymlfile, mp3file):
        user = self.me()
        cloudcast = Cloudcast.from_yml(ymlfile, user)
        _ = self.upload(cloudcast, mp3file)


@dataclass
class Artist:

    key: str
    name: str

    m: Optional[Mixcloud] = None

    @staticmethod
    def from_json(data):
        return Artist(data["slug"], data["name"])

    @staticmethod
    def from_yml(artist):
        return Artist(slugify(artist), artist)


@dataclass
class User:

    key: str
    name: str
    m: Optional[Mixcloud] = None

    _metadata: Optional[Dict] = None

    @staticmethod
    def from_json(data, m=None):
        if "username" in data and "name" in data:
            return User(data["username"], data["name"], m=m)

    def __repr__(self):
        return "<User:{}>".format(self.name)

    def __str__(self):
        return repr(self)

    def _get_metadata(self):
        url = "{}/{}/?metadata=1".format(self.m.api_root, self.name)
        r = get(url)
        data = r.json()
        return data["metadata"]["connections"]

    def cloudcast(self, key):
        url = "{}/{}/{}".format(self.m.api_root, self.key, key)
        r = get(url)
        data = r.json()
        return Cloudcast.from_json(data)

    def cloudcasts(self, limit=None, offset=None, all=False):
        data = get_many(
            "{}/{}/cloudcasts/".format(self.m.api_root, self.key), limit, offset
        )
        return [Cloudcast.from_json(d, m=self.m) for d in data["data"]]

    def playlist(self, key):
        r = get("{}/{}/playlists/{}".format(self.m.api_root, self.key, key))
        data = r.json()
        return Playlist.from_json(data, m=self.m)

    def playlists(self):
        pl = self.metadata.get("playlists")
        if pl:
            for playlist in get_all(pl):
                yield Playlist.from_json(playlist)

    @property
    def metadata(self):
        if not self._metadata:
            self._metadata = self._get_metadata()
        return self._metadata


@dataclass
class Playlist:

    key: str
    url: str
    name: str
    owner: str
    slug: str
    cloudcast_count: Optional[int] = 0
    created_time: Optional[datetime.datetime] = None
    updated_time: Optional[datetime.datetime] = None

    m: Optional[Mixcloud] = None

    def cloudcasts(self, limit=None, offset=None, all=False):
        url = "{}{}cloudcasts".format(API_ROOT, self.key)
        if all:
            data = get_all(url)
        else:
            data = get_many(url, limit=limit, offset=offset)
        for cast in data:
            yield Cloudcast.from_json(cast, m=self.m)

    @staticmethod
    def from_json(d, m=None):
        ctime = (
            dateutil.parser.parse(d["created_time"]) if "created_time" in d else None
        )
        mtime = (
            dateutil.parser.parse(d["updated_time"]) if "updated_time" in d else None
        )
        return Playlist(
            d["key"],
            d["url"],
            d["name"],
            User.from_json(d["owner"]),
            d["slug"],
            d.get("cloudcast_count", 0),
            ctime,
            mtime,
            m=m,
        )


@dataclass
class Cloudcast:

    key: str
    url: str
    name: str
    tags: Optional[List["Tag"]] = None
    created_time: Optional[datetime.datetime] = None
    updated_time: Optional[datetime.datetime] = None
    play_count: Optional[int] = 0
    favorite_count: Optional[int] = 0
    comment_count: Optional[int] = 0
    listener_count: Optional[int] = 0
    repost_count: Optional[int] = 0
    pictures: Optional[Dict] = None
    slug: Optional[int] = None
    user: Optional[User] = None
    hidden_stats: Optional[bool] = None
    audio_length: Optional[int] = 0

    _description: Optional[str] = ""
    _sections: Optional[List["Section"]] = None

    m: Optional[Mixcloud] = None

    @staticmethod
    def from_json(d, m=None):
        if "sections" in d:
            sections = Section.list_from_json(d["sections"])
        else:
            sections = None
        desc = d.get("description")
        tags = Tag.list_from_json(d["tags"])
        user = User.from_json(d["user"])
        created_time = dateutil.parser.parse(d["created_time"])
        updated_time = dateutil.parser.parse(d["updated_time"])
        pictures = d.get("pictures")
        return Cloudcast(
            d["key"],
            d["url"],
            d["name"],
            tags,
            created_time,
            updated_time,
            d.get("play_count"),
            d.get("favorite_count"),
            d.get("comment_count"),
            d.get("listener_count"),
            d.get("repost_count"),
            pictures,
            d["slug"],
            user,
            d.get("hidden_stats"),
            d["audio_length"],
            desc,
            sections,
            m,
        )

    def _load(self):
        url = "{}{}".format(self.m.api_root, self.key)
        r = get(url)
        d = r.json()
        self._sections = Section.list_from_json(d["sections"])
        self._description = d["description"]

    @property
    def sections(self):
        """
        Depending on the data available when the instance was created,
        it may be necessary to fetch data.
        """
        if self._sections is None:
            self._load()
        return self._sections

    @property
    def description(self):
        """
        May hit server. See Cloudcast.sections
        """
        if self._description is None:
            self._load()
        return self._description

    @property
    def picture(self):
        return self.pictures["large"]

    @staticmethod
    def from_yml(f, user):
        setup_yaml()
        d = yaml.load(f, Loader=yaml.FullLoader)
        name = d["title"]
        sections = [Section.from_yml(s) for s in d["tracks"]]
        key = slugify(name)
        tags = d["tags"]
        description = d["desc"]
        created_time = None
        c = Cloudcast(key, name, sections, tags, description, user, created_time)
        return c


@dataclass
class Section:

    start_time: datetime
    track: "Track"

    @staticmethod
    def from_json(d):
        return Section(d["start_time"], Track.from_json(d["track"]))

    @staticmethod
    def list_from_json(d):
        return [Section.from_json(s) for s in d]

    @staticmethod
    def from_yml(d):
        artist = Artist.from_yml(d["artist"])
        track = d["track"]
        return Section(d["start"], Track(track, artist))


@dataclass
class Track:

    name: str
    artist: Artist

    @staticmethod
    def from_json(d):
        return Track(d["name"], Artist.from_json(d["artist"]))


@dataclass
class Tag:
    key: str
    url: str
    name: str

    @staticmethod
    def from_json(d):
        return Tag(d["key"], d["url"], d["name"])

    @staticmethod
    def list_from_json(d):
        return [Tag.from_json(t) for t in d]

    def __str__(self):
        return self.name

    def __repr__(self):
        return str(self)
