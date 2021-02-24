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
    video: null
};

function youtubeInit() {
    let tag = makeElement('script', {src: 'https://www.youtube.com/iframe_api'})
    var firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);  
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
    let usePlayer = isMobileView() ? SETTINGS.player_mobile : SETTINGS.player;
    if (!usePlayer || !PLAYER.ready) {
        return true;
    }
    let link = e.target;
    if (link.tagName.toLowerCase() == 'img') {
        link = link.parentElement;
    }
    let wrap = document.getElementById('player_wrap');
    wrap.style.display = 'block';
    wrap.addEventListener('click', closePlayer);
    wrap.appendChild(makeElement('div', {id: "player"}));
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
    scrollToVideo(ELEMENT_BY_VIDEO_ID[videoId]);
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
