# CubedTube Tutorial

This document will guide you through creating your own CubedTube website.

NOTE: If you do end up using this software, please let me know through either
an email or a watch/star on GitHub!

## Project Structure

The server is intended to be a static webapp with an optional Flask powered
backend. The data is scraped from the YouTube API into an SQLite database
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

## Setup and Installation

CubedTube requieres [Python > 3.6](https://www.python.org/downloads/). This
can be somewhat complicated given your setup and goals so I recommend finding
a tutorial that's specific to your needs. That being said, I recommend you
use a virtual environment to prevent future pain.

The next step is to install CubedTube and all it's dependencies:

```bash
pip install cubedtube
```

And that's it!

## Setup

The minimal application consists solely of the scraper and frontend components.
For this to work you'll need to create a folder with two files inside of it:

 - `playlists.yaml` - The public part of your configuration which mostly
   includes YouTube playlists but also other site-specific things.
 - `credentials.yaml` - The secret part of your configuration such as API
   keys and installation details.

One thing to keep in mind is that `playlists.yaml` is safe to share and upload
to GitHub, but `credentials.yaml` should be kept secure (and never ever
uploaded to GitHub).

### credentials.yaml

WARNING: if `credentials.yaml` is inadvertently uploaded to GitHub, all
credentials containeed within MUST be changed.

A minimal `credentials.yaml` file would look like this:

```yaml
site_name: my_cubedtube_site
scraper:
  yt_api_key: my_youtube_api_key
```

You can get the YouTube Data API token by following the instructions over at
[developers.youtube.com](https://developers.google.com/youtube/v3/getting-started).
I would recommend using a new gmail account for creating the key in case of
inadvertent misuse or inadvertant leaks.

### playlists.yaml

For `playlists.yaml`, it's a bit more complicated. See
[HermitTube](https://github.com/stevarino/hermit-tube/) for a more complete
example, but a minimal example would be:

```yaml
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
    active: false
    channels:
      - name: Machine Learning at Google I/O 2019
        playlist: https://www.youtube.com/playlist?list=PLOU2XLYxmsIKW-llcbcFdpR9RjCfYHZaV
      - name: Accessibility at Google I/O 2019
        playlist: https://www.youtube.com/playlist?list=PLOU2XLYxmsIIOSO0eWuj-6yQmdakarUzN
        videos:
          - Es8ghP2M-m4
          - bTodlNvQGfY
```

Important things to note:

The `title` is required and used as your page title.

The `series` contains a set of playlists that are designed to go together as
part of a whole. Each series entry has a title (human friendly) and a slug (a
shorter name used within the database and app). Also one of your series should
have the field `default: true` as that will be what users see when they first
enter the site. One last option is `active: false`. By default all series are
active and therefore scraped every time. By setting `active: false` you can
skip series which you don't expect to be updated, saving time and quota.

Within a series is `channels` containing a `name`, and either a `playlist` or
`channel` field and optionally a list of `videos` to manually add. The `channel`
field should be set to the actual YouTube channel id and not the short-url. 
Regardless if you use `playlist` or `channel`, `name` must match across series
if you want to link channels across series.

## Scraping Videos

With this all set up, the final step is to pull in all the video metadata. The
first time you run this, CubedTube will create a database (`db.sqlite3`) to
store data in. Subsequent runs will keep updating the database.

To run the scraper:

 - Open a terminal or command line window.
 - Change directories to where `credentials.yaml` and `playlists.yaml` are
   stored.
 - If using a virtual environment, make sure its active.
 - Run the following:

```bash
cubedtube scraper --full
```

NOTE: The `--full` argument tells the scraper to scrape every regardless of if
the series is active or not. Subsequent runs should likely omit that argument
to save time and quota.

This should take up to a few minutes as the site combs through all the playlists
and videos. Once that's done you should have a `db.sqlite3` file with the data. You can use [DB Browser](https://sqlitebrowser.org/) to poke inside if
you want.

### Restarting

If `playlists.yaml` was not set up correctly, just delete the database file and
try again. It's that easy.

## Rendering the Frontend

Now you're ready for the final part of this introduction: making a website. To
do this simply type the following:

```bash
cubedtube frontend
```

This will generate HTML, CSS, and JavaScript files in a freshly created 
`output` directory. This can easily be previewed by running the command below
and loading the webpage to `localhost:8000`.

```bash
python -m http.server -d output
```

You should see a minimal site, ready to be used. This can either be used as-is
for your own viewing, uploaded to a shared hosting provider for sharing with
friends, or using as the basis for a more complicated webapp using nginx.

# Next Steps

From here there are a lot of options. [hermit.tube](https://www.hermit.tube)
is run with a Flask backend for storing user profiles, cloud storage for
reliable storage of user data, memcached to ensure speed and reliablity, and
backend workers to keep things moving.
