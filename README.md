# CubedTube

CubedTube is a webapp that aims to be a video viewer focused on three
aspects: time, creator (channel), and series (or seasons). This makes it 
possible for viewers to seamlessly bounce between different creators while 
watching a series unfold, discovering new creators involved in the series
and watching the story unfold with the creators together.

CubedTube started off as [hermit.tube](https://hermit.tube) - a way to watch
all of the [HermitCraft](http://hermitcraft.com) seasons and follow your hermits
in order. However as the project developed and I became more familiar with the
YouTube space, a general solution seemed ideal.

## Motivation

The first reason I created this site was I wanted to easily watch a HermitCraft 
season in order while bouncing between series.

The second was I wanted to build a low-dependency, simple and understandable
web app. I decided to make the actual content static to simplify hosting (and
as an extra challenge). But this is built with minimal requirements, consisting of
[peewee](https://github.com/coleifer/peewee) as a database ORM, the awesome
[Pako](https://nodeca.github.io/pako/) library for some data compression magic,
and a dynamic image-loader javascript library to make sure we don't DDOS YouTube.

An important factor of this project is that the code remains understandable and
approachable for those learning this craft. If you find this site helpful or have
any questions, I would love to hear from you.

## Features

 - Watch videos in chronological order across several channels.
 - Videos are automatically queued for uninterrupted watching.
 - Stored progress across subsequent loads, both through local storage and
   through the cloud.
 - Watch a select set of channels through multiple profiles.
 - Easily swap between profiles without losing your place.
 - Desktop and mobile friendly!
 - Installable as an app (pwa).
 - Modular footprint - the webapp can be run as a standalone HTML website, 
   optionally with a Flask app for OAuth and Cloud Storage, optional
   memcached support, and optional backend worker for async cloud writes.

## Planned Features

 - Cross platform video viewing (youtube/twitch/etc).
 - Promotion videos between videos (livestream announcements, events, etc)

## Project Structure

The server is intended to be a static HTML website with a Flask powered
backend. The data is scraped from the YouTube API into an sqlite database
and then processed into JSON and HTML files for server uplaod.

Key files include:

 - `playlists.yaml` - The main data structure, contains series (a HC season), 
   channels in the season, and playlists per channel.
 - `credentials.yaml` - Secrets of the app, things like salts and API tokens.
 - `db.sqlite3` - Created at runtime, contains all video information.
 - `scraper/` - Scrapes the YouTube API and processes them into the database.
 - `frontend/` - Processes through the database and builds JSON data files
   for use on the website. Also builds the HTML files using Jinja2.
 - `backend/` - Code that runs the Flask backend webapp. Handles authentication
   and user login.
 - `worker/` - Optionally runs in the background to help the backend service
   be more efficient.

# Setup and Installation

## Installation

## Minimal Setup

The minimal application consists solely of the scraper and frontend components.

Two data files are required: `playlists.yaml` which mostly includes YouTube
playlists but also other site-specific things, and `credentials.yaml` which
contains the secrets of the site. Basically `playlists.yaml` is safe to share
and upload to GitHub, but `credentials.yaml` should be kept secure (and never
ever uploaded to GitHub).

WARNING: if `credentials.yaml` is inadvertently uploaded to GitHub, all
credentials containeed within MUST be changed.

A minimal `credentials.yaml` file would look like this:

```
scraper:
  yt_api_key: my_youtube_api_key
```

You can get the YouTube Data API token by following the instructions over at
[developers.youtube.com](https://developers.google.com/youtube/v3/getting-started).
I would recommend using a new gmail account for creating the key, in case of
misuse or inadvertant leaks.

For `playlists.yaml`, it's a bit more complicated. See HermitTube for a more
complete example, but a minimal example would be:

```
title: Google I/O

series:
  - title: Google I/O 2021
    slug: gio2021
    default: true
    channels:
      - name: All Google I/O 2021 Q&As
        playlist: https://www.youtube.com/playlist?list=PLOU2XLYxmsIJwWXScAwCG5vSEQbwQsC0F
      - name: All Google I/O 2021 Demos
        playlist: https://www.youtube.com/playlist?list=PLOU2XLYxmsILU62c5HdPY5EQnUATTk04_
  - title: Google I/O 2019
    slug: gio2019
    channels:
      - name: Machine Learning at Google I/O 2019
        playlist: https://www.youtube.com/playlist?list=PLOU2XLYxmsIKW-llcbcFdpR9RjCfYHZaV
      - name: Accessibility at Google I/O 2019
        playlist: https://www.youtube.com/playlist?list=PLOU2XLYxmsIIOSO0eWuj-6yQmdakarUzN
        videos:
          - Es8ghP2M-m4
          - bTodlNvQGfY
```

Important things to note is the `title` is required and used as your page
title. The `series` contains a list of series, where each video shoudl be
part of the whole series. And within a series is `channels` containing
a name, and either a playlist or channel field and optionally a lsit of
videos to manually add.

NOTE: WIP, more coming soon.

