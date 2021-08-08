# CubedTube

CubedTube is a webapp video viewer focused on three aspects: time, creator
(channel), and series (or seasons). This makes it possible for viewers to 
seamlessly bounce between different creators while watching a series unfold, 
discovering new creators involved in the series and watching the story unfold 
with the creators together.

It's basically a YouTube playlist multiplexer.

CubedTube started off as [hermit.tube](https://hermit.tube) (
[git repo](https://github.com/stevarino/hermit-tube)) - a way to watch
all of the [HermitCraft](http://hermitcraft.com) seasons and follow your hermits
in order. However as the project developed and I became more familiar with the
YouTube space, a general solution seemed ideal.

Want to build your own? [Check out the tutorial!](https://github.com/stevarino/cubed-tube/blob/master/docs/tutorial.md)

## Motivation

The first reason I created this site was I wanted to easily watch a HermitCraft 
season in order while bouncing between series.

The second was I wanted to build a low-dependency, simple, and understandable
web app. I decided to make the actual content static to simplify hosting (and
as an extra challenge). But this is built with minimal requirements, consisting 
of [peewee](https://github.com/coleifer/peewee) as a database ORM, the awesome
[Pako](https://nodeca.github.io/pako/) library for some data compression magic,
and a dynamic image-loader javascript library to make sure we don't DDOS 
YouTube.

An important factor of this project is that the code remains understandable and
approachable for those learning this craft. If you find this site helpful or 
have any questions, I would love to hear from you.

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
 - Better CSS/Theming support.
