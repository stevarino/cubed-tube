/*
    This file includes the common details needed across scripts and the
    initialization details for the client app.
*/

// scroll tracker timeout timer, to prevent hundreds of actions per scroll
var scrollTimeout = null

// scroll to epoch data structure, used for converting scroll pos to time.
var scrollToEpoch = []

const MONTHS = [
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"
];

var BROWSE_CONTROLS = {
    'ArrowLeft': browsePrevVideo,
    'ArrowRight': browseNextVideo,
    ' ': browsePlayVideo,
}

// cached channel lookup metadata, keyed by name and index
var CHANNELS_BY_NAME = {}
var CHANNELS_BY_INDEX = {}
var ELEMENT_BY_VIDEO_ID = {}

window.onload = function() {
    loadSettings();
    let userPromise = initUser().then(renderProfileMenu);
    initDropdown()
    if (document.getElementById('loading') === null) {
        if (document.getElementById('channels') !== null) {
            document.getElementById('channels').style.display = 'none';
        }
        return;
    }
    window.addEventListener('scroll', function(e) {
        if (scrollTimeout !== null) {
            window.clearTimeout(scrollTimeout)
        }
        var pos = window.scrollY;
        scrollTimeout = window.setTimeout(function() {
            onScrollEvent(pos);
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
        } else if (PLAYER.obj === null && e.key in BROWSE_CONTROLS) {
            if (e.target.tagName.toLowerCase() == 'input') {
                return;
            }
            BROWSE_CONTROLS[e.key](e);
            e.preventDefault();
        } else {
            // console.log(e.key);
        }
    });

    document.getElementById('modal').addEventListener('click', hideModal);

    youtubeInit();
    userPromise.finally(() => {
        loadSeries();
    });
}

function onScrollEvent(pos) {
    getProfile().scroll = getScrollPos(pos);
    saveState();
    markVideoActive(pos);
}

function renderProfileMenu() {
    let menu = document.getElementById("settings");
    let items = Array.from(document.getElementsByClassName('profile_item'));
    for (let i = 0; i < items.length; i++) {
        items[i].parentElement.removeChild(items[i]);
    }
    listProfiles().forEach((profile) => {
        menu.appendChild(
            makeElement(
                'li', {class: 'profile_item'},
                makeElement('a', {
                    href: '#',
                    innerText: profile.profile,
                    click: function(e) {
                        closeMenus();
                        e.preventDefault();
                        setActiveProfile(profile);
                        changeProfile();
                        return false;
                    }
                })
            )
        );
    });
}

/**
 * Reloads the profile on change, updating profile order and selecting channels.
 */
function changeProfile() {
    renderProfileMenu();
    getActiveChannels();
    chans = [];
    document.querySelectorAll('#channels input').forEach((el) => {
        let new_val = CHANNELS_BY_NAME[el.getAttribute('data-channel')].active;
        if (new_val) {
            chans.push(el.getAttribute('data-channel'));
        }
        let old_val = el.checked;
        if (new_val != old_val) {
            el.checked = new_val;
            updateCheckbox(el);
        }
    });

    let vids = document.getElementsByClassName('video');
    for (let i = 0; i < vids.length; i++) {
        let visible = CHANNELS_BY_NAME[vids[i].getAttribute('data-channel')].active;
        vids[i].style.display = (visible ? 'block' : 'none');
    }
    updateScrollPos();
    saveState();
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

/**
 * Close all menus.
 */
function closeMenus() {
    document.querySelectorAll('#menu > li').forEach((li) => {
        li.classList.remove('active_hover', 'active_click');
    });
    document.body.classList.remove('menu_active');
}

/**
 * Adds/removes/toggles menu list-item class for hovering effects.
 * 
 * @param {Event} e 
 */
function hoverMenu(e, action) {
    if (isMobileView()) {
        return;
    }
    let el = e.target;
    if (el.tagName.toLowerCase() == 'a') {
        el = el.parentElement;
        if (el.getElementsByTagName('ul').length == 0) {
            return true;
        }
    }

    document.querySelectorAll('#menu > li').forEach((li) => {
        li.classList.remove(`active_hover`);
    });
    el.classList[action](`active_hover`);
    return false;
}

function clickHandler(e) {
    document.querySelectorAll('#menu li').forEach((li) => {
        let submenu = li.querySelector('ul');
        if (submenu === null) {
            return;
        }
        if (li == e.target || li.contains(e.target)) {
            if (submenu.contains(e.target)) {
                li.classList.add('active_click');
            } else {
                li.classList.toggle('active_click');
            }
        } else {
            li.classList.remove('active_click');
        }
    });
}

/**
 * Initialize series selector dropdown.
 */
function initDropdown() {
    let mainMenu = document.querySelector('.menu-icon');
    mainMenu.addEventListener('click', (e) => {
        document.body.classList.toggle('menu_active');
    });

    document.body.addEventListener('click', clickHandler);

    document.querySelectorAll("#menu > li").forEach((menu) => {
        menu.childNodes.forEach((el) => {
            if (el.nodeType == 1 && el.tagName.toLowerCase() == 'a') {
                el.addEventListener('keydown', (e) => {
                    if (e.key == ' ' || e.key.toLowerCase() == 'enter') {
                        console.log('keydown', e);
                        e.preventDefault();
                        e.stopPropagation();
                        clickHandler(e);
                    }
                });
            }
        });
        menu.addEventListener('mouseenter', (e) => hoverMenu(e, 'add'));
        menu.addEventListener('mouseleave', (e) => hoverMenu(e, 'remove'));
    });
    let dropdown = document.getElementById('seasons');
    if (dropdown === null) {
        return
    }
    window.all_series.forEach((s) => {
        let li = document.createElement('li');
        let link = document.createElement('a');
        link.setAttribute('href', '#');
        link.setAttribute('data-series', s[0]);
        link.innerText = s[1]
        li.appendChild(link);
        dropdown.appendChild(li);
        link.onclick = function() {
            setSeries(this.getAttribute('data-series'));
            closeMenus();
            // if we're  not on the home page (has a loading message), go there
            if (document.getElementById('loading') == null) {
                window.location = '/';
                return;
            }
            clearSeries();
            loadSeries();
            renderProfileMenu();
            return false;
        };
    });

    document.getElementById('form').addEventListener(
        'click', (e) => {e.stopPropagation()});

    // doc-id/callback list of buttons.
    let buttons = {
        login: loginClick,
        settings_link: showSettings,
        profile_new: createProfile,
    };
    for (const [id, callback] of Object.entries(buttons)) {
        if (!document.getElementById(id)) continue;
        document.getElementById(id).addEventListener('click', (e) => {
            e.preventDefault();
            callback(e);
        });
    }
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
    let active = e.target.checked;
    let profile = getProfile();
    toggleVideos(ch_id, active);
    updateCheckbox(e.target);
    updateScrollPos();
    profile.ch = getChannelStateString();
    saveState();
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
}

/**
 * Quick check if we're using a mobile stylesheet layout
 */
function isMobileView() {
    let menuButton = document.getElementsByClassName('menu-button')[0];
    return window.getComputedStyle(menuButton).display == 'block';
}


/**
 * Polls the server for updates and promos available.
 */
function fetchUpdate() {
    let d = new Date().getTime();
    // req.overrideMimeType("application/json");
    makeRequest({
        url: `/data/${getSeries()}/updates.json?${d}`,
        json: true,
    }).then((response) => {
        let vid = document.querySelector(
            `.video[data-video-id="${response.id}"]`);
        if (window.backend_version != response.version) {
            if (PLAYER.obj === null) {
                window.location.reload();
            } else {
                window.__REFRESH__ = 1;
            }
        }
        if (vid === null) {
            processUpdate(response, []);
        }
    }).catch((err) => {
        console.log('Error during fetchUpdate:', err);
    });
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
    // req.overrideMimeType("application/json");
    makeRequest({
        url: `/data/${getSeries()}/updates/${next.hash}.json`,
        json: true,
    }).then((response) => {
        stack.unshift(response);
        processUpdate(response.next, stack);
    }).catch((err) => {
        console.log('Error during processUpdate:', err);
    });
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
