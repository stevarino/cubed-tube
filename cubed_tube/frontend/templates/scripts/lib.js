ON_MODAL_CLOSE = null;

function clearObject(obj) {
    Object.keys(obj).forEach(function(key) { delete obj[key]; });
}

function shallowEqualObjects(obj1, obj2) {
    const keys1 = Object.keys(obj1);
    const keys2 = Object.keys(obj2);
  
    if (keys1.length !== keys2.length) {
        return false;
    }
  
    for (let key of keys1) {
        if (obj1[key] !== obj2[key]) {
            return false;
        }
    }
  
    return true;
}
  

function makeRequest({method='GET', url='', headers={}, params='', creds=false,
                      json=false, arraybuffer=false} = {}) {
    // https://stackoverflow.com/a/30008115/4001895
    return new Promise((res, rej) => {
        var xhr = new XMLHttpRequest();
        xhr.open(method, url);
        xhr.onload = function() {
            if (this.status >=200 && this.status < 300) {
                if (json) {
                    res(JSON.parse(xhr.responseText));
                } else if (arraybuffer) {
                    res(xhr.response);
                } else {
                    res(xhr.responseText);
                }
            } else {
                rej({status: this.status, statusText: this.statusText});
            }
        }
        xhr.onerror = function () {
            rej({status: this.status, statusText: xhr.statusText});
        };
        if (arraybuffer) {
            xhr.responseType = 'arraybuffer';
        }
        if (headers) {
            for (const [key, val] of Object.entries(headers)) {
                xhr.setRequestHeader(key, val);
            }
        }
        if (creds) {
            xhr.withCredentials = true;
        }
        // We'll need to stringify if we've been given an object
        // If we have a string, this is skipped.
        if (params && typeof params === 'object') {
            params = makeParams(params);
        }
        xhr.send(params);
    });
}

function makeGetRequest(endpoint, args, creds) {
    if (window.API_DOMAIN === '') return;
    let queryString = (args !== undefined) ? '?' + makeParams(args) : '';
    let request = {
        url: `//${window.API_DOMAIN}${endpoint}${queryString}`,
        json: true,
    }
    if (creds === true) {
        request.creds = true;
    }
    return makeRequest(request);
}


/**
 * Given an object, converts it into a key=val&key2=val2 string.
 * 
 * @param {Object} params 
 * @returns String
 */
function makeParams(params) {
    return Object.keys(params).map(function (key) {
        return `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`;
    }).join('&')
}

/**
 * Element Creation convenience function. Should be fast.
 * @param {String} tagName 
 * @param {Object} properties 
 * @param  {...Element} children 
 */
 function makeElement(tagName, properties, ...children) {
    let el = document.createElement(tagName);
    Object.keys(properties).forEach((k) => {
        if (['innerText', 'innerHTML'].includes(k)) {
            el[k] = properties[k];
        } else if (['change', 'click', 'mouseenter', 'mouseleave', 'keydown'].includes(k)) {
            el.addEventListener(k, properties[k]);
        } else {
            el.setAttribute(k, properties[k]);
        }
    });

    children.forEach(child => {
        el.appendChild(child)
    });
    return el;
}

function logJson(obj) {
    console.log(JSON.stringify(obj, null, 2));
}

function parseQueryString(url, multiple_vals) {
    let args = {};
    let parts = url.split('?');
    if (parts.length == 1) {
        return args;
    }
    parts[1].split('&').forEach(arg => {
        let pair = arg.split('=');
        if (pair.length == 1) {
            return;
        }
        let key = decodeURIComponent(pair[0]);
        let val = decodeURIComponent(pair[1]);
        if (multiple_vals !== undefined) {
            if (!(key in args)) {
                args[key] = [];
            }
            args[key].push(val);
        } else {
            args[key] = val;
        }
    });
    return args;
}

function showModal(onclose) {
    let container = document.getElementById('modal');
    document.body.classList.add('modal');
    container.style.display = 'block';
    ON_MODAL_CLOSE = onclose;
    return container;
}

function hideModal() {
    let container = document.getElementById('modal');
    container.style.display = 'none';
    container.classList.remove(
        ...Array.from(container.classList.values())
    );
    document.body.classList.remove('modal');
    if (ON_MODAL_CLOSE !== null && ON_MODAL_CLOSE !== undefined) {
        ON_MODAL_CLOSE();
        ON_MODAL_CLOSE = null;
    }
}

/**
 * https://github.com/rafgraph/fscreen
 */

var fscreen_api = (() => {
    const key = {
        fullscreenEnabled: 0,
        fullscreenElement: 1,
        requestFullscreen: 2,
        exitFullscreen: 3,
        fullscreenchange: 4,
        fullscreenerror: 5,
        fullscreen: 6,
    };
    
    const webkit = [
        'webkitFullscreenEnabled',
        'webkitFullscreenElement',
        'webkitRequestFullscreen',
        'webkitExitFullscreen',
        'webkitfullscreenchange',
        'webkitfullscreenerror',
        '-webkit-full-screen',
    ];
    
    const moz = [
        'mozFullScreenEnabled',
        'mozFullScreenElement',
        'mozRequestFullScreen',
        'mozCancelFullScreen',
        'mozfullscreenchange',
        'mozfullscreenerror',
        '-moz-full-screen',
    ];
    
    const ms = [
        'msFullscreenEnabled',
        'msFullscreenElement',
        'msRequestFullscreen',
        'msExitFullscreen',
        'MSFullscreenChange',
        'MSFullscreenError',
        '-ms-fullscreen',
    ];
    
    const vendor =
        ('fullscreenEnabled' in document && Object.keys(key)) ||
        (webkit[0] in document && webkit) ||
        (moz[0] in document && moz) ||
        (ms[0] in document && ms) ||
        [];
        
        // prettier-ignore
    return {
        requestFullscreen: element => element[vendor[key.requestFullscreen]](),
        requestFullscreenFunction: element => element[vendor[key.requestFullscreen]],
        get exitFullscreen() { return document[vendor[key.exitFullscreen]].bind(document); },
        get fullscreenPseudoClass() { return `:${vendor[key.fullscreen]}`; },
        addEventListener: (type, handler, options) => document.addEventListener(vendor[key[type]], handler, options),
        removeEventListener: (type, handler, options) => document.removeEventListener(vendor[key[type]], handler, options),
        get fullscreenEnabled() { return Boolean(document[vendor[key.fullscreenEnabled]]); },
        set fullscreenEnabled(val) {},
        get fullscreenElement() { return document[vendor[key.fullscreenElement]]; },
        set fullscreenElement(val) {},
        get onfullscreenchange() { return document[`on${vendor[key.fullscreenchange]}`.toLowerCase()]; },
        set onfullscreenchange(handler) { return document[`on${vendor[key.fullscreenchange]}`.toLowerCase()] = handler; },
        get onfullscreenerror() { return document[`on${vendor[key.fullscreenerror]}`.toLowerCase()]; },
        set onfullscreenerror(handler) { return document[`on${vendor[key.fullscreenerror]}`.toLowerCase()] = handler; },
    };
})();
