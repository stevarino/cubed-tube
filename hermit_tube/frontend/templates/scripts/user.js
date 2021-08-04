/*
    user.js is concerned with user state through the STATE global, and the
    storing and retrieval of that information.
*/

// Selected channels and scroll posstion by series (added channels are hidden)
var STATE = {}
    /**
     * {
     *      series (hc7) = [
     *          {
     *              'profile' = str              name
     *              'ts' = new Date().getTime()  timestamp
     *              'ch' = str(bytearray)        binary-stored inverted channel selection
     *              'scroll' = int               timestamp of current scroll position
     *           }
     *      ]
     * }
     */

var SETTINGS = {};
    /**
     * {
     *      player = bool           use integrated player
     *      autoplay = bool         autoplay integrated player on click
     *      use_fullscreen = bool   fullscreen integrated player
     *      series = string (hc7)   current series/season selected
     *      profile = int (0)       current profile selected
     * }
     */

// global user variables
var USER = {
    LOGGED_IN: false,

    // timer object used for series. Needs to be cleared on series update.
    UPDATE_TIMER: 0,

    // Delay before state can be uploaded.
    STATE_UPLOAD_TIMER: 0,
    STATE_UPLOAD_NEEDED: false,

    STATUS_TIMER: 0,
}

async function initUser() {
    if (window.API_DOMAIN == '') {
        document.getElementById('login').style.display = 'none';
        initLocalState();
        return;
    }
    USER.STATUS_TIMER = window.setInterval(sendUserStatus, 60000);
    await getUserState().catch(() => {
        initLocalState();
        createSeries(getSeries());
    });
    STATE = await migrateState(STATE);
}

async function getUserState() {
    return new Promise((resolve, reject) => {
        callBackendServer().then(response => {
            STATE = response.state;
            resolve();
        }).catch(reject);
    });
}

function callBackendServer(request) {
    default_request = {
        url: `//${window.API_DOMAIN}/app/user_state`, 
        creds: true,
        json: true,
    };

    if (request === undefined) {
        request = JSON.parse(JSON.stringify(default_request));
    }
    Object.keys(default_request).forEach((key) => {
        if (!(key in request)) {
            request[key] = default_request[key];
        }
    });

    return new Promise((resolve, reject) => {
        makeRequest(request).then((response) => {
            if (response.error === undefined) {
                // Received user state.
                markUserLoggedIn();
                return resolve(response);
            } else if (response.error === 'unknown') {
                // User is logged in, but no state.
                markUserLoggedIn(true);
            } else if (response.error === 'unauthenticated') {
                // User is not logged in...
            } else {
                console.log('Error, unrecognized response:', response);
            }
            return reject();
        }).catch((err) => {
            // TODO: retry with exponential backoff
            console.log('Error during getUserState:', err);
            return reject();
        });
    });
}

function migrateState(state) {
    // profile.accessed => profile.ts
    for (const profiles of Object.values(state)) {
        for (const profile of profiles) {
            if ('accessed' in profile) {
                profile.ts = profile.accessed;
                delete profile.accessed;
            }
        }
    }
    // trash
    if (null in STATE) {
        delete STATE[null];
    }
    // migrate channel strings
    let promises = [];
    for (const series in state) {
        let profiles = state[series];
        promises.push(new Promise((resolve, reject) => {
            if (profiles.length > 0 && ('channels' in profiles[0])) {
                requestSeries(series).then((series_data) => {
                    console.log(`Migrating ${series}`, series_data);
                    for (let i = 0; i < profiles.length; i++) {
                        profiles[i].ch = getChannelStateString(
                            profiles[i].channels, series_data);
                        delete profiles[i].channels;
                    }
                    resolve();
                });
            } else {
                resolve();
            }
        }));
    }
    return Promise.all(promises).then(()=>{return state;});
}

function markUserLoggedIn(upload_needed=false) {
    USER.LOGGED_IN = true;
    USER.STATE_UPLOAD_NEEDED = upload_needed;
    document.getElementById('login').innerText = 'Log Out'
}

function initLocalState() {
    STATE = loadFromStorage('state');
    if (STATE === null) {
        STATE = {};
    }
    return STATE
}

function loginClick() {
    let endpoint = USER.LOGGED_IN ? 'logout' : 'login';
    let redirect = encodeURIComponent(document.location);
    document.location = `//${API_DOMAIN}/${endpoint}?r=${redirect}`;
}

/**
 * Convenience function.
 */
function saveState(upload) {
    getProfile().ts = new Date().getTime();
    saveToStorage('state', STATE);

    if (upload === false) return;
    scheduleUploadState();
}

function scheduleUploadState() {
    if (!USER.LOGGED_IN) {
        return;
    }
    USER.STATE_UPLOAD_NEEDED = true;
    if (USER.STATE_UPLOAD_TIMER !== 0) {
        return;
    }
    uploadState();
    USER.STATE_UPLOAD_TIMER = setInterval(function() {
        uploadState();
    }, 60000);
}

function uploadState(force) {
    if (USER.STATE_UPLOAD_NEEDED === false && force === undefined) {
        clearInterval(USER.STATE_UPLOAD_TIMER);
        USER.STATE_UPLOAD_TIMER = 0;
        return;
    }
    console.log('Uploading State');

    callBackendServer({
        method: 'POST',
        params: JSON.stringify(STATE),
    }).then(response => {
        let profile = getProfile();
        STATE = response.state;
        let profiles = listProfiles();
        let found = false;
        let areYouMyProfile = (lhv, rhv) => {
            return lhv.profile === rhv.profile && lhv.ch === rhv.ch
        }
        if ('id' in profile) {
            areYouMyProfile = (lhv, rhv) => lhv.id === rhv.id
        }
        
        for (const p of profiles) {
            if (areYouMyProfile(p, profile)) {
                found = true;
                SETTINGS.profile = getProfileIndex(p);
                break;
            }
        }
        if (!found) {
            // currently active profile is likely deleted
            // this is awkward...
            window.location.reload();
        }
        renderProfileMenu();
    }).catch(console.log);
}

function saveSettings() {
    saveToStorage('settings', SETTINGS);
}

function loadSettings() {
    let settings_defaults = [
        ['player', true],
        ['autoplay', true],
        ['use_fullscreen', true],
    ];
    
    SETTINGS = this.loadFromStorage('settings');
    let list = document.getElementById('settings');
    if (SETTINGS === null) {
        SETTINGS = {};
    }
    let save = false;
    for (const [key, val] of settings_defaults) {
        if (SETTINGS[key] === undefined) {
            SETTINGS[key] = val;
            save = true;
        }
    }
    if (save) {
        saveSettings();
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

function createSeries(series) {
    if (series in STATE) {
        return;
    }
    STATE[series] = [{
        'profile': 'default',
        'ts': new Date().getTime(),
        'ch': '',
        'scroll': 0,
    }];
    SETTINGS.series = series;
    SETTINGS.profile = 0;
    saveSettings();
    saveState();
}

function createProfile() {
    let name = prompt("New profile name:", "");
    if (name === null) {
        return;
    }
    let series = STATE[getSeries()];
    let profile = JSON.parse(JSON.stringify(getProfile()));
    delete profile.id
    profile.profile = name;
    profile.ts = new Date().getTime();
    SETTINGS.profile = series.length;
    saveSettings()
    series.push(profile);
    saveState();
    changeProfile();
}

function deleteProfile(profile) {
    if (profile === undefined) {
        profile = getProfile();
    }
    if (listProfiles().length <= 1) {
        // TODO: Put note here about minimum profile counts...
        return;
    }
    let i = getProfileIndex(profile);
    if (i == SETTINGS.profile) {
        SETTINGS.profile = getProfileIndex(listProfiles()[1]);
    }
    let profiles = STATE[getSeries()];
    profiles[i] = {id: profile.id, ts: (new Date().getTime())};

    saveState();
    changeProfile();
}

function renameProfile(profile) {
    if (profile === undefined) {
        profile = getProfile();
    }
    let name = prompt("New profile name:", profile.profile);
    if (name === null) {
        return;
    }
    profile.profile = name;
    changeProfile();
    saveState();
}

/**
 * Save channels to saved state via bit array.
 */
function getChannelStateString(channelNames, series) {
    let names = {}
    if (series !== undefined) {
        for (const [key, val] of Object.entries(series.channels)) {
            val.index = key;
            names[val.name] = val;
        }
    } else {
        names = CHANNELS_BY_NAME;
    }
    var channels = [];
    if (channelNames !== undefined) {
        channelNames.forEach(ch => {
            if (names[ch] !== undefined) {
                channels.push(parseInt(names[ch].index) - 1);
            }
        });
    } else {
        document.querySelectorAll('#channels input').forEach(el => {
            if (!el.checked) {
                let ch = names[el.getAttribute('data-channel')];
                channels.push(parseInt(ch.index) - 1);
            }
        });
    }
    if (channels.length == 0) {
        return '';
    }
    var bits = new Uint8Array(
        Math.floor(Math.max(...channels) / 8) + 1)
    channels.forEach(ch => {
        let index = Math.floor(ch / 8);
        bits[index] = bits[index] | (2 ** (ch % 8))
    });
    return btoa(String.fromCharCode.apply(null, bits));
}

/**
 * Returns a list of channels from the active profile.
 */
function getActiveChannels() {
    let channels = loadChannelsFromState(getProfile().ch);
    for (const [name, isActive] of Object.entries(channels)) {
        CHANNELS_BY_NAME[name].active = isActive;
    }
    return channels;
}

/**
 * Returns a bit map of {channel_name => bool}, optionally updating global
 * channel objects' active field.
 */
function loadChannelsFromState(channelString) {
    let channels = {};
    Object.keys(CHANNELS_BY_NAME).forEach(name => {
        channels[name] = true;
    });
    var bits = atob(channelString).split('').map(byte => {
        return byte.charCodeAt(0);
    });
    for (const [index, chan] of Object.entries(CHANNELS_BY_INDEX)) {
        let val = parseInt(index) - 1;
        let byte = Math.floor(val / 8);
        let offset = val % 8;
        if (byte >= bits.length) {
            continue;
        }
        if (bits[byte] & (2 ** offset)) {
            channels[chan.name] = false;
        }
    }
    return channels;
}

/**
 * Returns a list of profiles in order of last accessed (current first).
 */
function listProfiles(recursive=true) {
    let profiles = [...STATE[getSeries()]].filter(p => {
        return 'profile' in p
    });
    let profile = null;
    if (recursive) {
        profile = getProfile();
    }
    profiles.sort((a, b) => {
        if (a == profile) {
            return -1;
        }
        if (b == profile) {
            return 1;
        }
        return b.ts - a.ts;
    });
    return profiles;
}

/**
 * Returns the currently active series (hc7).
 */
function getSeries() {
    if (SETTINGS.series !== null && SETTINGS.series !== undefined) {
        return SETTINGS.series;
    }
    let series = loadFromStorage('series');
    if (series === null) {
        series = window.series;
    }
    SETTINGS.series = series;
    saveSettings()
    return series;
}

/**
 * Returns the currently active profile object, creating if necessary.
 */
function getProfile() {
    function _resetProfile() {
        let profile = listProfiles(false)[0];
        let index = getProfileIndex(profile);
        if (index === -1) {
            throw "Profile not found";
        }
        SETTINGS.profile = index;
        saveSettings()
    }
    
    if (SETTINGS.profile === undefined 
            || STATE[getSeries()][SETTINGS.profile] === undefined
            || STATE[getSeries()][SETTINGS.profile].profile === undefined) {
        _resetProfile();
    }
    return STATE[SETTINGS.series][SETTINGS.profile];
}

function getProfileIndex(profile) {
    let profiles = STATE[getSeries()];
    for(let i = 0; i < profiles.length; i++) {
        if (shallowEqualObjects(profile, profiles[i])) {
            return i
        }
    }
    return -1
}


function setActiveProfile(profile) {
    let index = getProfileIndex(profile);
    console.log("Prpfile index: ", index)
    if (index === -1) {
        console.log("Unable to find profile...")
        index = 0;
    }
    SETTINGS.profile = index;
    saveSettings();
}

function setSeries(series) {
    createSeries(series);
    SETTINGS.series = series;
    SETTINGS.profile = getProfileIndex(listProfiles(false)[0]);
    saveSettings();
}

function logSeries() {
    logJson(STATE[getSeries()]);
}

function logProfile() {
    logJson(getProfile());
}

function logProfiles() {
    logJson(listProfiles());
}

function sendUserStatus() {
    makeGetRequest('/app/user_poll', {
        status: PLAYER.video === null ? 'idle' : 'video',
        is_mobile: isMobileView() ? '1' : '0',
        is_logged_in: USER.LOGGED_IN ? '1': '0',
    });
}
