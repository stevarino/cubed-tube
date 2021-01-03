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
I got bored writing CRUD queries over and over) and a dynamic image-loader
javascript library to make sure we don't ddos YouTube.

## Project Structure

The server is intended to be a static HTML website. The data is scraped from
the YouTube API into an sqlite database and then processed into JSON and
HTML files for server uplaod.

Key files include:

 - `playlists.yaml` - The main data structure, contains series (a HC season), 
   channels in the season, and playlists per channel.
 - `db.sqlite3` - Runtime only, contains all the scanned information.
 - `models.py` - The ORM models used for interacting with the database.
 - `scan.py` - Scrapes the YouTube API and processes them into the database.
 - `render.py` - Processes through the database and builds JSON data files
   for use on the website. Also builds the HTML files in a really janky way.