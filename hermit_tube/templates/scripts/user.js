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
     *      player_mobile
     *      player
     *      autoplay
     *      profile
     *      series
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
}

async function initUser() {
    let state = await getUserState().then((state) => {
        return state;
    }).catch(() => {
        return loadFromStorage('state');
    });
    STATE = await migrateState(state);
    saveState();
}

async function getUserState() {
    return new Promise((resolve, reject) => {
        makeRequest({
            url: `//${window.API_DOMAIN}/app/user_state`, 
            creds: true,
            json: true,
        }).then((response) => {
            // expecting a json response
            if (response.error === undefined) {
                // Received user state.
                console.log('Received State from Server');
                markUserLoggedIn();
                return resolve(response.state);
            } else if (response.error === 'unknown') {
                // User is logged in, but no state.
                markUserLoggedIn(true);
            } else if (response.error === 'unauthenticated') {
                // User is not logged in...
            } else {
                console.log('Error, unrecognized response:', response);
            }
        }).catch((err) => {
            console.log('Error during request:', err);
        });
        return reject();
    });
}

function migrateState(state) {
    for (const profiles of Object.values(state)) {
        for (const profile of profiles) {
            if ('accessed' in profile) {
                profile.ts = profile.accessed;
                delete profile.accessed;
            }
        }
    }
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
        saveState();
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

function uploadState() {
    if (USER.STATE_UPLOAD_NEEDED === false) {
        clearInterval(USER.STATE_UPLOAD_TIMER);
        USER.STATE_UPLOAD_TIMER = 0;
        return;
    }
    console.log('Uploading State');
    makeRequest({
        method: 'POST',
        url: `//${window.API_DOMAIN}/app/user_state`,
        creds: true,
        params: JSON.stringify(STATE),
        json: true,
    }).then((response) => {
        if (response.error === undefined) {
            STATE = response.state;
        } else {
            console.log("Request error: ", response);
        }
    }).catch((err) => {
        console.log("Request failed: ", err);
    })
}

function saveSettings() {
    saveToStorage('settings', SETTINGS);
}

function loadSettings() {
    SETTINGS = this.loadFromStorage('settings');
    if (SETTINGS === null) {
        SETTINGS = { player: true, autoplay: true };
        saveSettings()
    }
    if (SETTINGS.player_mobile === undefined) {
        SETTINGS.player_mobile = false;
        saveSettings()
    }
    if (document.getElementById('opt_player') === null) {
        return;
    }
    document.getElementById('opt_player').checked = SETTINGS.player;
    document.getElementById('opt_player').addEventListener('change', (e) => {
        SETTINGS.player = document.getElementById('opt_player').checked;
        saveSettings();
    });
    document.getElementById('opt_player_mobile').checked = SETTINGS.player_mobile;
    document.getElementById('opt_player_mobile').addEventListener('change', (e) => {
        SETTINGS.player_mobile = document.getElementById('opt_player_mobile').checked;
        saveSettings();
    });
    document.getElementById('opt_autoplay').checked = SETTINGS.autoplay;
    document.getElementById('opt_autoplay').addEventListener('change', (e) => {
        SETTINGS.autoplay = document.getElementById('opt_autoplay').checked;
        saveSettings();
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
    profile.profile = name;
    profile.ts = new Date().getTime();
    SETTINGS.profile = series.length;
    saveSettings()
    series.push(profile);
    saveState();
    changeProfile();
}

function deleteProfile() {
    let profile = getProfile();
    if (listProfiles().length <= 1) {
        // TODO: Put note here about minimum profile counts...
        return;
    }
    let newProfile = listProfiles()[1];
    let profiles = STATE[getSeries()];
    let i = getProfileIndex(profile)
    if (i == -1) {
        return console.error("Profile not found.", profile, profiles);
    }
    profiles.splice(i, 1);
    let j = getProfileIndex(newProfile);
    SETTINTGS.profile = j;


    saveState();
    changeProfile();
}

function renameProfile() {
    let profile = getProfile();
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
    console.log("channels before: ", channels);
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
    let profiles = [...STATE[getSeries()]];
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
    if (SETTINGS.series !== undefined) {
        return SETTINGS.series;
    }
    series = loadFromStorage('series');
    if (series === null) {
        series = window.series;
    }
    SETTINGS.series = series;
    saveSettings()
    return series;
}

/**
 * Returns the currently active profile.
 */
function getProfile() {
    if (SETTINGS.series === undefined || SETTINGS.profile === undefined) {
        let profile = listProfiles(false)[0];
        let index = getProfileIndex(profile);
        if (index === -1) {
            index = 0;
        }
        SETTINGS.profile = index;
        saveSettings()
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
    SETTINGS.series = series;
    SETTINGS.profile = getProfileIndex(listProfiles(false)[0]);
    saveSettings();
}
