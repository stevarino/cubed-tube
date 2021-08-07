/*
    YouTube Player API integration
*/

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
    video: null,
};

function youtubeInit() {
    let tag = makeElement('script', {src: 'https://www.youtube.com/iframe_api'})
    var firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

    // don't bubble up to #player if full screen
    document.getElementById('player_controls').addEventListener('click', (e) => {
        if (isFullScreen()) e.stopPropagation();
    });
    window.addEventListener('popstate', (e) => {
        if (PLAYER.obj !== null && (e.state === null || e.state.view === undefined)) {
            closePlayer();
        }
    });
    let buttons = document.getElementsByClassName('material-icons');
    for (let i=0; i<buttons.length; i++) {
        buttons[i].addEventListener('click', handleMediaButtons)
    }
    document.onfullscreenchange = onFullScreenChange;
}

function onYouTubeIframeAPIReady() {
    console.log("YouTube Player Loaded.")
    PLAYER.ready = true;
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
    showModal(destroyPlayer);
    history.pushState({'view': 'player'}, document.title);
    PLAYER.video = link.getAttribute('data-video-id');
    sendPlayStats();
    console.log('playing video ', PLAYER.video);
    PLAYER.obj = new YT.Player('player_iframe', {
        height: '390',
        width: '640',
        videoId: PLAYER.video,
        events: {
            'onReady': (e) => {e.target.playVideo()},
            'onStateChange': onPlayerStateChange
        },
        playerVars: {
            showinfo: 0,
            fs: 0
        }        
    });
    PLAYER.obj.getIframe().focus();
    if (SETTINGS.use_fullscreen) {
        document.getElementById('modal').requestFullscreen();
        screen.orientation.lock('landscape').then().catch();
    }
    e.preventDefault();
    return false;
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
    PLAYER.state = e.data;
    if (PLAYER.state === 2) {
        document.getElementById('modal').classList.add('paused');
    } else {
        document.getElementById('modal').classList.remove('paused');
    }
    if (PLAYER.state != 0) {
        return;
    }
    if (!SETTINGS.autoplay) {
        closePlayer();
        return;
    }
    playNextVideo();
}

function playNextVideo(forward=true) {
    let videoId = findNextVideo(PLAYER.video, forward);
    if (videoId == null) {
        closePlayer();
        return;
    }
    PLAYER.video = videoId;
    sendPlayStats();
    PLAYER.obj.loadVideoById({ 'videoId': videoId });
}

function playPrevVideo() {
    playNextVideo(false);
}

function closePlayer() {
    hideModal();
}

/**
 * Destroys the embedded YouTube player, resets state, and restores the site.
 */
function destroyPlayer() {
    PLAYER.obj.destroy();
    PLAYER.obj = null;
    PLAYER.state = null;
    document.getElementById('player_iframe').innerHTML = '';

    if (PLAYER.video) {
        let vid = ELEMENT_BY_VIDEO_ID[PLAYER.video];
        window.setTimeout(() => {scrollToVideo(vid);}, 500);
    }
    PLAYER.video = null;

    if (isFullScreen()) {
        document.exitFullscreen();
    }

    if (history.state && history.state.view) {
        history.back();
    }

    if (window.__REFRESH__ !== undefined) {
        window.location.reload();
    }
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

function isFullScreen() {
    return document.fullscreenElement !== null
}

function onFullScreenChange(e) {
    if (isFullScreen()) {
        document.getElementById('modal').classList.add('fullscreen');
    } else {
        document.getElementById('modal').classList.remove('fullscreen');
    }
}

function toggleFullScreen() {
    if (isFullScreen()) {
        document.exitFullscreen();
    } else {
        document.getElementById('modal').requestFullscreen();
    }
}

function handleMediaButtons(e) {
    e.stopPropagation();
    let text = e.target.innerText;
    let actions = {
        stop: closePlayer,
        next: playNextVideo,
        prev: playPrevVideo,
        paws: pausePlayer,
        play: pausePlayer,
        full: toggleFullScreen,
    }
    for (var i=0; i<e.target.classList.length; i++) {
        if (actions[e.target.classList[i]]) {
            actions[e.target.classList[i]]();
            return;
        }
    }
}

function sendPlayStats() {
    makeGetRequest('/app/play_count',{
        channel: ELEMENT_BY_VIDEO_ID[PLAYER.video].getAttribute('data-channel'),
        series: getSeries(),
    });
}
