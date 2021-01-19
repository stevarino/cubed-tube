# HermitBook

This is a way to watch [Hermitcraft](http://hermitcraft.com) seasons, allowing
you to follow your select hermits in order!

## Motivation

The first reason I created this site was I wanted to easily watch a HermitCraft 
season in order while bouncing between series.

The second was I wanted to build a low-dependency, simple and understandable
web page. I decided to make the actual content static to simplify hosting (and
as an extra challenge). But this is built with minimal requirements, consisting of
[peewee](https://github.com/coleifer/peewee) as a database ORM (needed after
I got bored writing CRUD queries over and over), the awesome
[Pako](https://nodeca.github.io/pako/) library for some data compression magic,
and a dynamic image-loader javascript library to make sure we don't DDOS YouTube.

## Features

 - Watch HermitCraft videos in chronological order across several channels.
 - Videos are automatically queued for uninterrupted watching.
 - The website remembers your position in the playlist across subsequent loads.
 - Watch a select set of channels through profiles.
 - Easily swap between profiles without losing your place.
 - Desktop and mobile friendly!

## Planned Features

 - Install as app (pwa).
 - Cross platform video viewing (youtube/twitch/etc).
 - Save, load, and merge user state centrally on the server.
 - Improved embedded player.
 - Promotion videos between videos (livestream announcements, swag, etc)
 - Video analytics?

## Project Structure

The server is intended to be a static HTML website. The data is scraped from
the YouTube API into an sqlite database and then processed into JSON and
HTML files for server uplaod.

Key files include:

 - `playlists.yaml` - The main data structure, contains series (a HC season), 
   channels in the season, and playlists per channel.
 - `db.sqlite3` - Created at runtime, contains all the scanned information.
 - `main.py` - The main entry point of this program.
 - `lib/models.py` - The ORM models used for interacting with the database.
 - `lib/wsgi.py` - A Flask app for an authenticated control plane (WIP).
 - `lib/scan.py` - Scrapes the YouTube API and processes them into the database.
 - `lib/render.py` - Processes through the database and builds JSON data files
   for use on the website. Also builds the HTML files using Jinja2.
