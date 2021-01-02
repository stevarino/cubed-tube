const MONTHS = [
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"
];

// Selected channels and scroll posstion by series (added channels are hidden)
var STATE = {}
    /**
     * {
     *      series (hc7) = [
     *          {
     *              'profile' = str
     *              'accessed' = new Date().getTime()
     *              'channels' = [
     *                  'channelIdStr'
     *              ],
     *              'scroll' = int
     *           }
     *      ]
     * }
     */

// scroll tracker timeout timer, to prevent hundreds of actions per scroll
var scrollTimeout = null

// scroll to epoch data structure.
var scrollToEpoch = []

var SETTINGS = {};

// embedded YouTube player
var PLAYER = {
    obj: null,
    // state enum: -1 unplayed, 0 fin, 1 play, 2 pause, 3 buff, 5 cued
    state: null,
    ready: false,
    controls: {
        'Escape': closePlayer,
        ' ': pausePlayer,
    },
    video: null
};

var BROWSE_CONTROLS = {
    'ArrowLeft': browsePrevVideo,
    'ArrowRight': browseNextVideo,
    ' ': browsePlayVideo,
}

// cached channel lookup metadata, keyed by name and index
var CHANNELS_BY_NAME = {}
var CHANNELS_BY_INDEX = {}

// timer object used for series. Needs to be cleared on series update.
var UPDATE_TIMER = 0;

window.onload = function() {
    loadSettings();
    initDropdown()
    if (document.getElementById('loading') === null) {
        document.getElementById('channels').style.display = 'none';
        return;
    }
    STATE = loadFromStorage('state');
    if (STATE === null) {
        STATE = {};
        saveToStorage('state', STATE);
    }
    window.addEventListener('scroll', function(e) {
        if (scrollTimeout !== null) {
            window.clearTimeout(scrollTimeout)
        }
        var pos = window.scrollY;
        scrollTimeout = window.setTimeout(function() {
            getProfile().scroll = getScrollPos(pos);
            saveToStorage('state', STATE);
            markVideoActive(pos);
        }, 300);
    });
    window.addEventListener('resize', function() {
        if (scrollTimeout !== null) {
            window.clearTimeout(scrollTimeout)
        }
        scrollTimeout = window.setTimeout(function() {
            updateScrollPos();
        }, 300);
    });
    document.body.addEventListener('keydown', (e) => {
        if (PLAYER.obj !== null && e.key in PLAYER.controls) {
            PLAYER.controls[e.key](e);
            e.preventDefault();
            return false;
        } else if (PLAYER.obj === null && e.key in BROWSE_CONTROLS) {
            BROWSE_CONTROLS[e.key](e);
            e.preventDefault();
            return false;
        } else {
            // console.log(e.key);
        }
    });
    loadSeries();
    renderProfileMenu();
}

function renderProfileMenu() {
    let menu = document.getElementById("settings");
    let items = Array.from(document.getElementsByClassName('profile_item'));
    for (let i = 0; i < items.length; i++) {
        items[i].parentElement.removeChild(items[i]);
    }
    let profiles = listProfiles();
    profiles.forEach(profile => {
        let li = htmlToElement("<li class='profile_item'><a href='#'></a></li>");
        let link = li.childNodes[0];
        link.innerText = profile.profile;
        link.addEventListener('click', (e) => {
            e.preventDefault();
            profile.accessed = new Date().getTime();
            console.log("Changing profile to ", profile);
            saveToStorage('state', STATE);
            changeProfile();
            return false;
        });
        menu.appendChild(li);
    });
}

/**
 * Reloads the profile on change, updating profile order and selecting channels.
 */
function changeProfile() {
    renderProfileMenu();
    let profile = getProfile();
    document.querySelectorAll('#channels input').forEach((el) => {
        let new_val = !profile.channels.includes(el.getAttribute('data-channel'));
        let old_val = el.checked;
        if (new_val != old_val) {
            el.checked = new_val;
            toggleChannels();
        }
    });
}

function markVideoActive(pos) {
    let lim = document.getElementById('header').getBoundingClientRect().bottom;
    var offset = document.body.getBoundingClientRect().top;
    let found = false;
    let start = new Date();
    let active = null;
    var actives = document.getElementsByClassName('activevid');
    while (actives.length > 0) {
        actives[0].classList.remove('activevid');
    }
    for (var i in scrollToEpoch) {
        if ((scrollToEpoch[i].pos + offset) >= lim && !found) {
            active = scrollToEpoch[i];
            found = true;
        }
    }
    if (active !== null) {
        active.video.classList.add('activevid');
    }
}

function onYouTubeIframeAPIReady() {
    PLAYER.ready = true;
}

function loadSettings() {
    SETTINGS = this.loadFromStorage('settings');
    if (SETTINGS === null) {
        SETTINGS = { player: true, autoplay: true };
        this.saveToStorage('settings', SETTINGS);
    }
    document.getElementById('opt_player').checked = SETTINGS.player;
    document.getElementById('opt_player').addEventListener('change', (e) => {
        SETTINGS.player = document.getElementById('opt_player').checked;
        console.log(SETTINGS);
        this.saveToStorage('settings', SETTINGS);
    })
    document.getElementById('opt_autoplay').checked = SETTINGS.autoplay;
    document.getElementById('opt_autoplay').addEventListener('change', (e) => {
        SETTINGS.autoplay = document.getElementById('opt_autoplay').checked;
        console.log(SETTINGS);
        this.saveToStorage('settings', SETTINGS);
    })
}

/**
 * Adds/removes/toggles menu list-item class for hovering effects.
 * 
 * @param {Event} e 
 */
function modifyMenu(e, action, className) {
    let el = e.target;
    if (el.tagName.toLowerCase() == 'a') {
        el = el.parentElement;
        if (el.getElementsByTagName('ul').length == 0) {
            return true;
        }
    }
    e.preventDefault();
    if (el.tagName.toLowerCase() == 'a') {}
    document.querySelectorAll('#menu > li').forEach((li) => {
        if (li != el) {
            li.classList.remove(`active_${className}`);
        }
    })
    el.classList[action](`active_${className}`);
    return false;
}

/**
 * Initialize series selector dropdown.
 */
function initDropdown() {
    let mainMenu = document.querySelector('.menu-icon');
    mainMenu.addEventListener('click', (e) => {
        console.log('click!');
        document.body.classList.toggle('menu_active');
    });
    document.querySelectorAll("#menu > li").forEach((menu) => {
        menu.childNodes.forEach((el) => {
            if (el.nodeType == 1 && el.tagName.toLowerCase() == 'a') {
                el.addEventListener('click', (e) => modifyMenu(e, 'toggle', 'click'));
                el.addEventListener('keydown', (e) => {
                    if (e.key == ' ' || e.key.toLowerCase() == 'enter') {
                        return modifyMenu(e, 'toggle', 'click')
                    }
                });
            }
        });
        menu.addEventListener('mouseenter', (e) => modifyMenu(e, 'add', 'hover'));
        menu.addEventListener('mouseleave', (e) => modifyMenu(e, 'remove', 'hover'));
    });
    let dropdown = document.getElementById('seasons');
    window.all_series.forEach((s) => {
        let li = document.createElement('li');
        let link = document.createElement('a');
        link.setAttribute('href', '#');
        link.setAttribute('data-series', s[0]);
        link.innerText = s[1]
        li.appendChild(link);
        dropdown.appendChild(li);
        link.onclick = function() {
            saveToStorage('series', this.getAttribute('data-series'));
            // if we're  not on the home page (has a loading message), go there
            if (document.getElementById('loading') == null) {
                window.location = '/';
                return;
            }
            clearSeries();
            loadSeries();
            return false;
        };
    });

    // doc-id/callback list of buttons.
    let buttons = {
        profile_new: createProfile,
        profile_rename: renameProfile,
        profile_delete: deleteProfile,
    };
    for (const [id, callback] of Object.entries(buttons)) {
        document.getElementById(id).addEventListener('click', (e) => {
            e.preventDefault();
            callback();
        });
    }
}

/**
 * Wrapper for localStorage.setItem.
 * 
 * @param {str} key 
 * @param {object} val 
 */
function saveToStorage(key, val) {
    try {
        localStorage.setItem(key, JSON.stringify(val));
    } catch (e) {
        console.log(e);
        return false;
    }
    localStorage.getItem(key);
}

/**
 * Wrapper for localStorage.getItem.
 * 
 * @param {str} key 
 */
function loadFromStorage(key) {
    try {
        val = localStorage.getItem(key);
        if (val === null) {
            return null;
        }
        return JSON.parse(val);
    } catch (e) {
        console.log(e)
        return null;
    }
}

/**
 * Loads a series from the server.
 */
function loadSeries() {
    let series = getSeries();
    console.log('Loading', series);
    if (!(series in STATE)) {
        STATE[series] = [{
            'profile': 'default',
            'accessed': new Date().getTime(),
            'channels': [],
            'scroll': 0,
        }];
        saveToStorage('state', STATE);
    } else if (!(STATE[series] instanceof Array)) {
        // one time migrate code
        STATE[series]['profile'] = 'default';
        STATE[series]['accessed'] = 0;
        STATE[series] = [STATE['series']];
    }

    var req = new XMLHttpRequest();
    req.overrideMimeType("application/json");
    req.open('GET', '/data/' + series + '/index.json', true);
    req.onreadystatechange = function() {
        if (req.readyState == 4) {
            if (req.status == "200") {
                renderSeries(req.responseText);
            } else {
                console.log('Error during request:', req);
            }
        }
    };
    req.send();

    if (UPDATE_TIMER !== 0) {
        clearInterval(UPDATE_TIMER);
    }
    UPDATE_TIMER = setInterval(fetchUpdate, 300000); // 5 minutes
}

/**
 * Returns the currently active series (hc7).
 */
function getSeries() {
    let series = loadFromStorage('series');
    if (series === null) {
        series = window.series;
    } else {
        window.series = series;
    }
    return series;
}

/**
 * Returns a list of profiles in order of last accessed (current first).
 */
function listProfiles() {
    let profiles = [...STATE[window.series]];
    profiles.sort((a, b) => b.accessed - a.accessed);
    return profiles;
}

/**
 * Returns the currently active profile.
 */
function getProfile() {
    return listProfiles()[0];
}

function createProfile() {
    let name = prompt("New profile name:", "");
    if (name === null) {
        return;
    }
    let profile = JSON.parse(JSON.stringify(getProfile()));
    profile.profile = name;
    profile.accessed = new Date().getTime();
    STATE[window.series].push(profile);
    saveToStorage('state', STATE);
    changeProfile();
}

function deleteProfile() {
    let profile = getProfile();
    if (listProfiles().length > 1) {
        let profiles = STATE[window.series];
        let i = profiles.indexOf(profile);
        console.log('deleting', i, JSON.parse(JSON.stringify(profiles)));
        if (i == -1) {
            console.error("Profile not found.", profile, profiles);
        } else {
            profiles.splice(i, 1);
            saveToStorage('state', STATE);
            changeProfile();
        }
    }
}

function renameProfile() {
    let profile = getProfile();
    let name = prompt("New profile name:", profile.profile);
    if (name === null) {
        return;
    }
    profile.profile = name;
    changeProfile();
    saveToStorage('state', STATE);

}

/**
 * Given a channel ID, shows or hides all videos from that channel.
 * 
 * @param {str} ch_id 
 * @param {bool} visible 
 */
function toggleVideos(ch_id, visible) {
    let vids = document.getElementsByClassName(`channel_${ch_id}`);
    for (let i = 0; i < vids.length; i++) {
        vids[i].style.display = (visible ? 'block' : 'none');
    }
}

/**
 * Checkbox onchange event handler, shows or hides videos based on check.
 * 
 * @param {Event} e 
 */
function toggleChannel(e) {
    let ch_id = e.target.getAttribute('data-channel');
    let visible = e.target.checked;
    let profile = getProfile();
    toggleVideos(ch_id, visible);
    let index = profile.channels.indexOf(ch_id);
    if (visible && index != -1) {
        profile.channels.splice(index, 1);
    } else if (!visible && index == -1) {
        profile.channels.push(ch_id);
    }
    updateCheckbox(e.target);
    updateScrollPos();
    saveToStorage('state', STATE);
}

function updateCheckbox(el) {
    let parent = el.parentElement;
    while (parent.tagName.toLowerCase() != 'li') {
        parent = parent.parentElement;
    }
    if (el.checked) {
        parent.classList.add('checked');
    } else {
        parent.classList.remove('checked');
    }
}

function toggleChannels() {
    let channel_map = {};
    document.querySelectorAll('#channels input').forEach((el) => {
        channel_map[el.getAttribute('data-channel')] = el.checked;
        updateCheckbox(el);
    });
    let vids = document.getElementsByClassName('video');
    for (let i = 0; i < vids.length; i++) {
        let visible = channel_map[vids[i].getAttribute('data-channel')];
        vids[i].style.display = (visible ? 'block' : 'none');
    }
    updateScrollPos();
    saveToStorage('state', STATE);
}

/**
 * Resets the content window to load a different series.
 */
function clearSeries() {
    document.querySelectorAll('#videos, #channels > *').forEach((el) => {
        el.parentElement.removeChild(el);
    });
    document.getElementById('loading').style.display = 'block';
}

/**
 * Parses a server response for a series and displays it.
 * 
 * @param {str} data JSON server response payload
 */
function renderSeries(data) {
    var series = JSON.parse(data);
    document.getElementById('loading').style.display = 'none';
    var content = document.getElementById('content');

    renderChannels(series.channels);

    var videos = document.createElement('div');
    videos.setAttribute('id', 'videos');
    content.appendChild(videos);

    for (let i = 0; i < series.videos.length; i++) {
        series.channel
        renderVideo(videos, series.videos[i]);
    }
    setSeriesState();
    loadDescriptions();
}

/**
 * Sets the series/videos as visible.
 */
function setSeriesState() {
    getProfile().channels.forEach((ch_id) => {
        toggleVideos(ch_id, false);
    });

    updateScrollPos();
    lazyload();
}

/**
 * String to HTML Element convenience function.
 * 
 * @param {str} html 
 */
function htmlToElement(html) {
    var template = document.createElement('template');
    template.innerHTML = html.trim();
    return template.content.firstChild;
}

/**
 * Renders the Channel Selection checkboxes and sets the global cache.
 * 
 * @param {Array} seriesChannels The series channels
 */
function renderChannels(seriesChannels) {
    function clearObject(obj) {
        Object.keys(obj).forEach(function(key) { delete obj[key]; });
    }
    clearObject(CHANNELS_BY_NAME);
    clearObject(CHANNELS_BY_INDEX);
    for (let i = 0; i < seriesChannels.length; i++) {
        let ch = seriesChannels[i];
        ch.index = i;
        CHANNELS_BY_NAME[ch.name] = ch;
        CHANNELS_BY_INDEX[i] = ch;
    }
    var channels = document.getElementById('channels');
    channels.appendChild(htmlToElement(`
        <li><span>Select <a id='selectall' href='#'>All</a> | 
        <a id='selectnone' href='#'>None</a></span></li>
    `));
    document.getElementById('selectall').addEventListener('click', (e) => {
        document.querySelectorAll('#channels input').forEach((el) => {
            el.checked = true;
            toggleChannel({ target: el });
        });
        e.preventDefault();
        return false;
    })
    document.getElementById('selectnone').addEventListener('click', (e) => {
        document.querySelectorAll('#channels input').forEach((el) => {
            el.checked = false;
            toggleChannel({ target: el })
        });
        e.preventDefault();
        return false;
    })
    Object.keys(CHANNELS_BY_NAME).sort().forEach(function(key) {
        channels.appendChild(renderChannelCheckbox(key, CHANNELS_BY_NAME[key]));
    });
}


/**
 * Renders a channel checkbox. All channel values are from the config so
 * HTML-injection safe.
 * 
 * @param {str} id 
 * @param {str} title 
 */
function renderChannelCheckbox(id, data) {
    let active = getProfile().channels.indexOf(id) == -1;
    let checked = active ? 'checked="checked"' : '';
    let root = htmlToElement('<li></li>');
    if (active) {
        root.classList.add('checked');
    }
    let label = htmlToElement(`<label for='channel_${id}'></label>`);
    root.appendChild(label);
    let input = htmlToElement(`
        <input type='checkbox' ${checked} id='channel_${id}'
            data-channel='${id}' />`);
    label.appendChild(input);

    let img = htmlToElement(
        `<img src='${data.thumb}' width='44' height='44' />`);
    img.setAttribute('alt', `${data.title}'s Logo`);
    label.appendChild(img);

    label.appendChild(document.createTextNode(data.t));
    input.addEventListener('change', toggleChannel);
    return root;
}


/**
 * Renders a date header if it has not been rendered yet.
 * 
 * @param {HTMLElement} videos 
 * @param {Object} vid 
 */
function renderDate(videos, vid) {
    let d = new Date(0);
    d.setUTCSeconds(vid.ts);
    let dateId = `date_${d.getFullYear()}${d.getMonth()}`;
    if (document.getElementById(dateId) === null) {
        let dateEl = document.createElement('h2');
        dateEl.setAttribute('id', `date_${d.getFullYear()}${d.getMonth()}`)
        dateEl.innerText = `${MONTHS[d.getMonth()]} ${d.getFullYear()}`;;
        videos.appendChild(dateEl);
    }
}

/**
 * Renders a video as an HTML Elment. Content generated by YouTube is safe,
 * but any content from the channel should be escaped.
 * 
 * @param {Object} vid 
 * @param {Object} ch 
 */
function renderVideo(videos, vid) {
    renderDate(videos, vid);
    let ch = CHANNELS_BY_INDEX[vid.ch];
    if (ch === undefined) {
        console.error(`channel not found: ${vid.ch}`)
    }

    let vidEl = htmlToElement(`
        <div
            class='video channel_${ch.name}'
            data-timestamp='${vid.ts}'
            data-video-id='${vid.id}'
            data-channel='${ch.name}'>
    `);

    let vidURL = `https://www.youtube.com/watch?v=${vid.id}`;
    let chURL = `https://www.youtube.com/channel/${ch.id}`;

    let title = htmlToElement(`
        <h3>
            <a href='${chURL}' target='_blank'>
                <img data-src='${ch.thumb}' width='44' height='44'
                    title='${ch.t}' alt='${ch.t}'
                    class="lazyload" />
            </a>
        </h3>
    `);

    title.appendChild(htmlToElement(`
        <a href='${chURL}?sub_confirmation=1' target='_blank'
            class='channel_subscribe'>Subscribe</a>
    `));

    let vidLink = htmlToElement(`<a href='${vidURL}' target='_blank'></a>`);
    vidLink.setAttribute('data-video-id', vid.id);
    vidLink.addEventListener('click', loadPlayer);
    vidLink.innerText = vid.t;
    title.appendChild(vidLink);
    title.appendChild(document.createElement('br'));
    title.appendChild(htmlToElement(`
        <a href='${chURL}' target='_blank' title='${ch.t} channel'
            class='channel_link'>${ch.t}</a>
    `))

    let d = new Date(0);
    d.setUTCSeconds(vid.ts);
    let month = MONTHS[d.getMonth()].substr(0, 3);
    title.appendChild(htmlToElement(`
        <span class='date'>${month} ${d.getDate()} ${d.getFullYear()}</span>
    `));


    vidEl.appendChild(title);

    let thumbLink = htmlToElement(`<a href='${vidURL}' target='_blank'></a>`);
    thumbLink.setAttribute('data-video-id', vid.id);
    thumbLink.addEventListener('click', loadPlayer);
    vidEl.appendChild(thumbLink);
    let thumb = htmlToElement(`
        <img
            data-src='https://i.ytimg.com/vi/${vid.id}/mqdefault.jpg'
            class="lazyload thumb" width='320' height='180' />`)
    thumb.setAttribute('alt', vid.t);
    thumb.setAttribute('title', vid.t);
    thumbLink.appendChild(thumb);

    vidEl.addEventListener('mouseenter', videoShowMoreLess);
    vidEl.addEventListener('mouseleave', videoHideMoreLess);

    videos.appendChild(vidEl);

    if (vid.hasOwnProperty('d')) {
        vidEl.appendChild(renderDescription(vid.d));
    }
}

function videoShowMoreLess(e) {
    let vid = e.target;
    let rect = vid.getBoundingClientRect();
    let para = vid.lastChild;
    if (para.tagName.toLowerCase() != 'p') {
        return;
    }
    let paraRect = para.getBoundingClientRect();
    let text = vid.classList.contains('expanded') ? 'Less' : 'More';

    let show = htmlToElement(`
        <span class="showmoreless">
            Show ${text}
        </span>`);
    show.addEventListener('click', videoExpand);
    vid.appendChild(show);
}

function videoHideMoreLess(e) {
    let vid = e.target;
    let span = vid.getElementsByClassName('showmoreless');
    if (span.length == 0) {
        return;
    }
    vid.removeChild(span[0]);
}

function videoExpand(e) {
    var vid = e.target.parentElement;
    vid.classList.toggle('expanded');
    updateScrollPos();
    let text = vid.classList.contains('expanded') ? 'Less' : 'More';
    let span = vid.getElementsByClassName('showmoreless');
    if (span.length == 0) {
        return;
    }
    span[0].innerText = 'Show ' + text;
}

/**
 * Converts scroll to timestamp.
 * 
 * @param {int} pos window.scrollY value
 */
function getScrollPos(pos) {
    // Converts scroll position to timestamp
    if (pos == 0) {
        return 0;
    }
    for (var i = 0; i < scrollToEpoch.length; i++) {
        let current = scrollToEpoch[i];
        if (current.pos < pos) continue;
        if (i == 0) return 0;

        let prev = scrollToEpoch[i - 1];
        let offset = (pos - prev.pos) / (current.pos - prev.pos);
        let ts = offset * (current.ts - prev.ts) + prev.ts;
        return ts;
    }
    return scrollToEpoch[scrollToEpoch.length - 1].ts;
}

/**
 * Converts stored timestamp to scroll position.
 */
function setScrollPos() {
    let ts = getProfile().scroll;
    for (var i = 0; i < scrollToEpoch.length; i++) {
        var current = scrollToEpoch[i];
        if (current.ts < ts) continue;
        if (i == 0) return 0;

        let prev = scrollToEpoch[i - 1];
        let offset = (ts - prev.ts) / (current.ts - prev.ts);
        let px = offset * (current.pos - prev.pos) + prev.pos;
        return px;
    }
}

/**
 * Recalculates the timeline and updates scroll position.
 */
function updateScrollPos() {
    updateTimeline();
    window.scrollTo(0, setScrollPos());
    markVideoActive(setScrollPos())
}

/**
 * Updates the global scrollToEpoch.
 */
function updateTimeline() {
    var offset = document.body.getBoundingClientRect().top;
    scrollToEpoch.length = 0;
    var els = document.getElementsByClassName('video');
    for (var i = 0; i < els.length; i++) {
        el = els[i];
        if (el.style.display == 'none') {
            continue;
        }
        scrollToEpoch.push({
            'ts': parseInt(el.getAttribute('data-timestamp')),
            'pos': el.getBoundingClientRect().top - offset,
            'video': el,
        });
    }
    console.log('updateTimeLine:', scrollToEpoch.length)
}

/**
 * Asynchronously load video descriptions. This saves >90% of playlist loading
 * latency.
 */
function loadDescriptions() {
    getDescriptions(0)
}

function getDescriptions(i) {
    let req = new XMLHttpRequest();
    req.overrideMimeType("application/json");
    req.open('GET', `/data/${window.series}/desc/${i}.json`, true);
    req.onreadystatechange = function() {
        if (req.readyState == 4) {
            if (req.status == "200") {
                renderDescriptions(i, req.responseText);
            } else {
                console.log('Error during request:', req);
            }
        }
    };
    req.send();
}

/**
 * Receives an XMLHttpRequest payload and loads the data into the appropriate
 * video descriptions.
 * @param {str} jsonText 
 */
function renderDescriptions(i, jsonText) {
    let descs = JSON.parse(jsonText);
    for (const [vid_id, desc] of Object.entries(descs.videos)) {
        let vid = document.querySelector(`.video[data-video-id="${vid_id}"]`);
        if (vid === null) {
            console.error("Unrecognized video id: ", vid_id);
        }
        vid.appendChild(renderDescription(desc));
    }
    if (descs.done == 0) {
        getDescriptions(i + 1);
    }
}

function renderDescription(desc) {
    para = document.createElement('p');
    desc.split(/(?:\r\n|\r|\n)/).forEach((text) => {
        // there are so many problems with this, but its good enough.
        // probably...
        text.split(/(https?:\/\/[^\s]+)/).forEach((part) => {
            if (part.startsWith('http')) {
                let link = htmlToElement(
                    `<a href="${part}" target='blank'>${part}</a>`);
                para.appendChild(link);
            } else {
                para.appendChild(document.createTextNode(part));
            }
        })
        para.appendChild(document.createElement('br'));
    });
    while (para.lastChild.nodeName.toLowerCase() == 'br') {
        para.removeChild(para.lastChild);
    }
    return para;
}

/**
 * Initialize the YouTube Embedded Player if available and play the clicked
 * video.
 * @param {Object} e onclick triggering event
 */
function loadPlayer(e) {
    if (!SETTINGS.player || !PLAYER.ready) {
        return true;
    }
    let link = e.target;
    if (link.tagName.toLowerCase() == 'img') {
        link = link.parentElement;
    }
    let wrap = document.getElementById('player_wrap');
    wrap.style.display = 'block';
    wrap.addEventListener('click', closePlayer);
    wrap.appendChild(htmlToElement('<div id="player"></div>'));
    PLAYER.video = link.getAttribute('data-video-id');
    console.log('playing video ', PLAYER.video);
    PLAYER.obj = new YT.Player('player', {
        height: '390',
        width: '640',
        videoId: PLAYER.video,
        events: {
            'onReady': onPlayerReady,
            'onStateChange': onPlayerStateChange
        }
    });
    PLAYER.obj.getIframe().focus();
    e.preventDefault();
    return false;
}

/**
 * Receives ready status when YouTube player is loaded.
 */
function onPlayerReady(e) {
    console.log('player ready');
    e.target.playVideo();
}

/**
 * YouTube Player State Change Event, with e.data being an enum corresponding
 * as follows: 
 *  
    -1 unplayed,
     0 video finished
     1 playing
     2 paused
     3 buffering
     5 cued

 * @param {Object} e YouTube Event
 */
function onPlayerStateChange(e) {
    console.log('player state change:', e.data, e);
    PLAYER.state = e.data;
    if (PLAYER.state != 0) {
        return;
    }
    if (!SETTINGS.autoplay) {
        closePlayer();
        return;
    }
    let videoId = findNextVideo(PLAYER.video);
    if (videoId == null) {
        closePlayer();
        return;
    }
    PLAYER.video = videoId;
    PLAYER.obj.loadVideoById({ 'videoId': videoId });
}

/**
 * Destroys the embedded YouTube player, resets state, and restores the site.
 */
function closePlayer() {
    document.getElementById('player_wrap').style.display = 'none';
    PLAYER.obj.destroy();
    PLAYER.obj = null;
    PLAYER.video = null;
    PLAYER.state = null;
    document.getElementById('player_wrap').innerHTML = '';
}

/**
 * Keypress event to play/pause the video.
 * @param {Object} e Keypress event
 */
function pausePlayer(e) {
    if (PLAYER.obj === null) {
        return true;
    }
    if (PLAYER.state == 2 || PLAYER.state == 5) {
        PLAYER.obj.playVideo();
    } else {
        PLAYER.obj.pauseVideo();
    }
}

/**
 * Given a video id, finds the next video id for the user's selected channels.
 * @param {str} videoId 
 */
function findNextVideo(videoId) {
    let videos = document.getElementsByClassName('video');
    found = false;
    for (let i = 0; i < videos.length; i++) {
        let other_id = videos[i].getAttribute('data-video-id');
        if (other_id == videoId) {
            found = true;
            continue;
        }
        if (!found) {
            continue;
        }
        if (videos[i].style.display == 'none') {
            continue;
        }
        return other_id;
    }
    return null;
}


/**
 * Polls the server for updates and promos available.
 */
function fetchUpdate() {
    let d = Date().getTime();
    let req = new XMLHttpRequest();
    req.overrideMimeType("application/json");
    req.open('GET', `/data/${window.series}/updates.json?d`, true);
    req.onreadystatechange = function() {
        if (req.readyState == 4) {
            if (req.status == "200") {
                let update = JSON.parse(req.responseText);
                let vid = document.querySelector(
                    `.video[data-video-id="${update.id}"]`);
                if (vid === null) {
                    processUpdate(update, []);
                }
            } else {
                console.log('Error during request:', req);
            }
        }
    };
    req.send();
}

/**
 * Recursively requests last several videos.
 * 
 * @param {Object} next 
 * @param {Array} stack 
 */
function processUpdate(next, stack) {
    if (next.id === null) {
        // Reached the end of the update chain. Options are:
        //   1) Refresh, potentially interrupting the user
        //   2) Increase the length of the update chain
        //   3) Nothing. Just let the user figure it out.

        // Personally I think (3) is the best option as that's how webpages
        // usually work.
        let header = document.querySelector('h1 a');
        header.style.color = '#f00';
        header.title = 'Too out of date to sync, please refresh';
    }
    let vid = document.querySelector(`.video[data-video-id="${next.id}"]`);
    if (vid !== null) {
        return renderUpdate(stack);
    }
    let req = new XMLHttpRequest();
    req.overrideMimeType("application/json");
    req.open('GET', `/data/${window.series}/updates/${next.hash}.json`, true);
    req.onreadystatechange = function() {
        if (req.readyState == 4) {
            if (req.status == "200") {
                let update = JSON.parse(req.responseText);
                stack.unshift(update)
                processUpdate(update.next, stack)
            } else {
                console.log('Error during request:', req);
            }
        }
    };
    req.send();
}

/**
 * Renders the videos as found via processUpdate.
 * 
 * @param {Array} stack 
 */
function renderUpdate(stack) {
    let videos = document.getElementById('videos')
    stack.forEach(update => {
        console.log(`Adding ${update.id}`);
        update.ch = CHANNELS_BY_NAME[update.chn].index
        renderVideo(videos, update)
    });
    lazyload();
}


function findAdjacentVideo(reverse) {
    let vid = document.querySelector('.activevid');
    let next = reverse ? 'previousElementSibling' : 'nextElementSibling';
    if (vid === null) return null;
    while (true) {
        vid = vid[next];
        if (vid === null) break;
        if (!vid.classList.contains('video')) continue;
        if (vid.style.display == 'none') continue;

        let header = document.getElementById('header').getBoundingClientRect().bottom;
        let scrollBy = vid.getBoundingClientRect().top - header - 10;
        console.log(
            'scrolling to ',
            vid.attributes['data-video-id'].value,
            scrollBy);

        window.scrollBy(0, scrollBy);
        break;
    }
}

function scrollToVideo(vid) {}

function browseNextVideo() {
    findAdjacentVideo(false);
}

function browsePrevVideo() {
    findAdjacentVideo(true);
}

function browsePlayVideo() {
    let vid = document.querySelector('.activevid');
    loadPlayer({ target: vid.querySelector('.thumb').parentElement });
}