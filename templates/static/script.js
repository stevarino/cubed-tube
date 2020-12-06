const MONTHS = [
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"
];

// Selected channels and scroll posstion by series (added channels are hidden)
var STATE = {}

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

window.onload = function () {
    loadSettings();
    initDropdown()
    if (document.getElementById('loading') === null) {
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
            STATE[window.series].scroll = getScrollPos(pos);
            saveToStorage('state', STATE);
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
    loadSeries();
}

function onYouTubeIframeAPIReady() {
    PLAYER.ready = true;
}

function loadSettings() {
    SETTINGS = this.loadFromStorage('settings')
    if (SETTINGS === null) {
        SETTINGS = {player: true, autoplay: true};
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
 * Initialize series selector dropdown.
 */
function initDropdown() {
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
    let series = loadFromStorage('series');
    if (series === null) {
        series = window.series;
    } else {
        window.series = series;
    }
    console.log('Loading', series);
    if (!(series in STATE)) {
        STATE[series] = {'channels': [], 'scroll': 0};
        saveToStorage('state', STATE);
    }

    var req = new XMLHttpRequest();
    req.overrideMimeType("application/json");
    req.open('GET', '/data/' + series + '.json', true);
    req.onreadystatechange = function () {
        if (req.readyState == 4) {
            if (req.status == "200") {
                renderSeries(req.responseText);
            } else {
                console.log('Error during request:', req);
            }
        }
    };
    req.send();
}

/**
 * Given a channel ID, shows or hides all videos from that channel.
 * 
 * @param {str} ch_id 
 * @param {bool} visible 
 */
function toggleVideos(ch_id, visible) {
    let vids = document.getElementsByClassName(`channel_${ch_id}`);
    for (let i=0; i<vids.length; i++) {
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
    toggleVideos(ch_id, visible);
    let index = STATE[window.series].channels.indexOf(ch_id);
    if (visible && index != -1) {
        STATE[window.series].channels.splice(index, 1);
    } else if (!visible && index == -1) {
        STATE[window.series].channels.push(ch_id);
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
        channel_map[getAttribute('data-channel')] = el.checked;
        updateCheckbox(el);
    });
    let vids = document.getElementsByClassName('video');
    for (let i=0; i<vids.length; i++) {
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

    document.querySelectorAll('#channels input')
    prevDate = '';
    for (let i=0; i<series.videos.length; i++) {
        let vid = series.videos[i];
        if (vid.t === null) {
            continue;
        }
        let d = new Date(0);
        d.setUTCSeconds(vid.ts);
        dateText = `${MONTHS[d.getMonth()]} ${d.getFullYear()}`
        if (prevDate != dateText) {
            let dateEl = document.createElement('h2');
            dateEl.innerText = dateText;
            videos.appendChild(dateEl);
            prevDate = dateText;
        }

        videos.appendChild(renderVideo(vid, series.channels[vid.ch]));
    }
    
    STATE[window.series].channels.forEach((ch_id) => {
        toggleVideos(ch_id, false);
    });

    updateScrollPos();
    lazyload();
    loadDescriptions();
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
 * Renders the Channel Selection checkboxes.
 * 
 * @param {Array} seriesChannels The series channels
 */
function renderChannels(seriesChannels) {
    let channelList = {};
    seriesChannels.forEach((ch) => {
        channelList[ch.name] = ch
    });
    var channels = document.getElementById('channels');
    channels.appendChild(htmlToElement(`
        <li><span>Select <a id='selectall' href='#'>All</a> | 
        <a id='selectnone' href='#'>None</a></span></li>
    `))
    document.getElementById('selectall').addEventListener('click', (e)=> {
        document.querySelectorAll('#channels input').forEach((el) => {
            el.checked = true;
            toggleChannel({target: el})
        });
        e.preventDefault();
        return false;
    })
    document.getElementById('selectnone').addEventListener('click', (e)=> {
        document.querySelectorAll('#channels input').forEach((el) => {
            el.checked = false;
            toggleChannel({target: el})
        });
        e.preventDefault();
        return false;
    })
    Object.keys(channelList).sort().forEach(function(key) {
        channels.appendChild(renderChannelCheckbox(
            key, channelList[key]));
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
    let active = STATE[window.series].channels.indexOf(id) == -1;
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
 * Renders a video as an HTML Elment. Content generated by YouTube is safe,
 * but any content from the channel should be escaped.
 * 
 * @param {Object} vid 
 * @param {Object} ch 
 */
function renderVideo(vid, ch) {
    vidEl = document.createElement('div');
    vidEl.classList.add('video');
    vidEl.classList.add(`channel_${ch['name']}`);
    vidEl.setAttribute('data-timestamp', vid.ts);
    vidEl.setAttribute('data-video-id', vid.id);
    vidEl.setAttribute('data-channel', ch.name);

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
    let month = MONTHS[d.getMonth()].substr(0,3);
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

    return vidEl;
}

function videoShowMoreLess(e) {
    let vid = e.target;
    let rect = vid.getBoundingClientRect();
    let para = vid.lastChild;
    if (para.tagName.toLowerCase() != 'p') {
        return;
    }
    let paraRect = para.getBoundingClientRect();
    let text = vid.classList.contains('expanded') ? 'Less': 'More';
    
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
    let text = vid.classList.contains('expanded') ? 'Less': 'More';
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
    for (var i=0; i<scrollToEpoch.length; i++) {
        let current = scrollToEpoch[i];
        if (current.pos < pos) continue;
        if (i == 0) return 0;

        let prev = scrollToEpoch[i-1];
        let offset = (pos - prev.pos) / (current.pos - prev.pos);
        let ts = offset * (current.ts - prev.ts) + prev.ts;
        return ts;
    }
    return scrollToEpoch[scrollToEpoch.length-1].ts;
}

/**
 * Converts stored timestamp to scroll position.
 */
function setScrollPos() {
    let ts = STATE[window.series].scroll;
    for (var i=0; i<scrollToEpoch.length; i++) {
        var current = scrollToEpoch[i];
        if (current.ts < ts) continue;
        if (i == 0) return  0;

        let prev = scrollToEpoch[i-1];
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
}

/**
 * Updates the global scrollToEpoch.
 */
function updateTimeline() {
    var offset = document.body.getBoundingClientRect().top;
    scrollToEpoch.length = 0;
    var els = document.getElementsByClassName('video');
    for (var i=0; i<els.length; i++) {
        el = els[i];
        if (el.style.display == 'none') {
            continue;
        }
        scrollToEpoch.push({
            'ts': parseInt(el.getAttribute('data-timestamp')),
            'pos': el.getBoundingClientRect().top - offset
        });
    }
    console.log('updateTimeLine:', scrollToEpoch.length)
}

/**
 * Asynchronously load video descriptions. This saves >90% of playlist loading
 * latency.
 */
function loadDescriptions() {
    var req = new XMLHttpRequest();
    req.overrideMimeType("application/json");
    req.open('GET', '/data/' + series + '.desc.json', true);
    req.onreadystatechange = function () {
        if (req.readyState == 4) {
            if (req.status == "200") {
                renderDescriptions(req.responseText);
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
function renderDescriptions(jsonText) {
    let descs = JSON.parse(jsonText);   
    let videos = document.getElementsByClassName('video');
    for (var i=0; i<videos.length; i++) {
        let vid = videos[i];
        let desc = descs[vid.getAttribute('data-video-id')]

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
        vid.appendChild(para);
    }
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
    document.body.addEventListener('keydown', (e) => {
        console.log(e);
        if (e.key in PLAYER.controls) {
            PLAYER.controls[e.key](e);
        }
    });
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
    PLAYER.obj.loadVideoById({'videoId': videoId});
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
    e.preventDefault();
    return false;
}

/**
 * Given a video id, finds the next video id for the user's selected channels.
 * @param {str} videoId 
 */
function findNextVideo(videoId) {
    let videos = document.getElementsByClassName('video');
    found = false;
    for(let i=0; i<videos.length; i++) {
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
