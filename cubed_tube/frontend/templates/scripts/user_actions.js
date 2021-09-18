ACTIONS = {
    TIMER: null,
    ACTIVE: false,
};


function initActions() {
    makeRequest({
        url: `//${window.API_DOMAIN}/app/actions`,
        creds: true,
        json: true,
    }).then((response) => {
        console.log('actions: ', response);
        USER.ACTIONS = response.actions;
        let login_li = document.getElementById('login').parentElement;
        let action_ul = makeElement('ul', {'aria-label': 'submenu'})
        let action_li = makeElement(
            'li', {class: 'submenus'}, 
            makeElement('a', {
                href: '#', 
                onclick: 'return false',
                innerText: 'Actions'
            }), action_ul);
        login_li.parentElement.insertBefore(action_li, login_li);
        addMenuEventListeners(action_li);

        response.actions.forEach((action) => {
            console.log(action.name)
            action_ul.appendChild(makeElement('li', {}, makeElement('a', {
                innerText: action.name,
                'data-action': action.id,
                click: clickActionMenu
            })))
        });
    });
}

function clickActionMenu(e) {
    e.preventDefault();
    e.stopPropagation();
    closeMenus();
    let action_id = e.target.getAttribute('data-action');
    USER.ACTIONS.forEach((action) => {
        if (action.id == action_id) {
            openActionModal(action);
            return false;
        }
    })
    return false;
}

function openActionModal(action) {
    let modal = showModal(closeActionModal);
    modal.classList.add('form');
    let form = document.getElementById('form');
    form.innerHTML = '';
    form.appendChild(makeElement('h2', {innerText: action.name}));
    action.form.fields.forEach((field) => {renderField(form, field)});
    form.appendChild(makeElement('p', {}, 
        makeElement('input', {
            'style': 'margin: 0 auto;',
            'type': 'submit',
            'click': submitActionMenu,
            'keydown': (e) => {
                if (e.key == ' ' || e.key.toLowerCase() == 'enter') {
                    e.preventDefault();
                    e.stopPropagation();
                    submitActionMenu(e);
                }
            }
        }),
        makeElement('input', {
            'type': 'hidden',
            'id': 'action_name',
            'name': 'action',
            'value': action.id,
        })
    ));
}

function closeActionModal() {
    ACTIONS.ACTIVE = false;
    document.getElementById('form').innerHTML = '';
    if (ACTIONS.TIMER !== null) {
        window.clearTimeout(ACTIONS.TIMER);
        ACTIONS.TIMER = null;
    }
}

function renderField(parent, field) {
    let keydownEvent = (e) => {
        if (e.key.toLowerCase() == 'enter') {
            e.preventDefault();
            e.stopPropagation();
            submitActionMenu(e);
        }
    }
    if (field.text !== undefined) {
        parent.appendChild(makeElement('p', {innerText: field.text}));
        return;
    }
    if (field.html !== undefined) {
        parent.appendChild(makeElement('p', {innerHTML: field.html}));
        return;
    }
    let label_text = field.id.toLowerCase().split('_').map((s) => {
            if (s == 'id') return 'ID'
            return s.charAt(0).toUpperCase() + s.substring(1)
        }).join(' ');
    let wrap = makeElement('p', {}, makeElement(
        'span', {'class': 'label', innerText: label_text}));
    parent.appendChild(wrap)
    if (field.type === undefined) {
        if (field.enum !== undefined) {
            field.type = 'select';
        } else {
            field.type = 'text';
        }
    }

    if (field.type === 'text') {
        wrap.appendChild(makeElement('input', {
            type: 'text',
            name: field.id,
            keydown: keydownEvent,
            class: 'modal_field',
        }));
    }
    if (field.type === 'textarea') {
        wrap.appendChild(makeElement('textarea', {
            name: field.id,
            class: 'modal_field',
        }));
    }
    if (field.type === 'select') {
        let sel = makeElement('select', {
            name: field.id,
            keydown: keydownEvent,
            class: 'modal_field',
        });
        wrap.appendChild(sel);
        field.enum.forEach((option) => {
            sel.appendChild(makeElement('option', {
                value: option, 
                innerText: option,
            }));
        });
    }
}

async function sendActionRequest(action_name, params) {
    if (ACTIONS.ACTIVE) {
        return;
    }
    ACTIONS.ACTIVE = true;
    try {
        var response = await makeRequest({
            url: `//${window.API_DOMAIN}/app/request_action?action=${action_name}`,
            method: 'POST',
            json: true,
            creds: true,
            params: JSON.stringify(params),
        });
    } catch (e) {
        ACTIONS.ACTIVE = false;
        ACTIONS.TIMER = null;
        console.log(e);
        return;
    }
    if (response.error !== undefined) {
        document.getElementById('form').appendChild(makeElement('p', {
            'style': 'color: red;',
            'innerText': response.error,
        }));
        ACTIONS.ACTIVE = false;
        return;
    }
    updateStatus(response.record.id, 0);
}

function submitActionMenu(e) {
    let fields = {}
    let form_name = document.getElementById('action_name').value
    Array.from(document.getElementsByClassName('modal_field')).forEach(f => {
        fields[f.getAttribute('name')] = f.value;
    });
    sendActionRequest(form_name, fields)
}

async function updateStatus(record_id, t) {
    if (t === undefined) {
        t = 0;
    }
    const response = await makeGetRequest(
        '/app/action_status', {id: record_id, t: t}, true);
    console.log('status response: ', response)
    const form = document.getElementById('form');

    
    if (response.error !== undefined) {
        // form.appendChild(makeElement('p', {
        //     'style': 'color: red;',
        //     'innerText': response.error,
        // }));
        // ACTIONS.ACTIVE = false;
        // ACTIONS.TIMER = null;
        // return;
    }
    
    if (response.records) {
        for (const record of response.records) {
            t = record.time;
            renderRecordStep(form, record);
        }
    }
    
    if (ACTIONS.ACTIVE) {
        // TODO: exponential backoff...
        ACTIONS.TIMER = setTimeout(updateStatus, 500, record_id, t);
    } else {
        ACTIONS.TIMER = null;
    }
}


function renderRecordStep(el, record) {
    t = record.time;
    let d = new Date(t * 1000);
    if (record.heading !== undefined) {
        el.appendChild(makeElement('h3', {
            'innerText': (
                d.toLocaleTimeString(undefined, {hour12: false})
                + ' ' + record.heading
            ),
        }))
        el.appendChild(makeElement('div', {'class': 'action_response'}));
    }
    var box = el.querySelectorAll(".action_response:last-child");
    if (box !== undefined && box.length > 0) {
        box = box[0]
    } else {
        el.appendChild(makeElement('h3', {
            'innerText': d.toLocaleTimeString(undefined, {hour12: false}),
        }))
        box = makeElement('div', {'class': 'action_response'});
        el.appendChild(box);
    }

    if (record.text !== undefined) {
        box.appendChild(makeElement('div', {'innerText': record.text}));
    }
    if (record.html !== undefined) {
        let div = makeElement('div', {
            'innerHTML': record.html,
            'style': 'overflow-x: auto;'
        })
        let dates = div.getElementsByClassName('format_time');
        for (let i=0; i<dates.length; i++) {
            let date = new Date(Number(dates[i].innerHTML) * 1000);
            let date_str = date.toLocaleDateString(undefined,  {
                year: 'numeric', month: 'numeric', day: 'numeric' });
            let time = date.toLocaleTimeString(undefined, {hour12: false});
            dates[i].innerHTML = `${date_str} ${time}`
        }

        let links = div.getElementsByClassName('action_link');
        for (let i=0; i<links.length; i++) {
            links[i].addEventListener('click', (e) => {
                let action = e.target.getAttribute('data-action');
                let params = JSON.parse(e.target.getAttribute('data-params'));
                sendActionRequest(action, params);
                e.preventDefault();
                return false;
            })
        }
        box.appendChild(div);
    }
    if (record.pre_text !== undefined) {
        box.appendChild(makeElement('div', {'style': 'overflow-x: auto;'},
            makeElement('pre', {'innerText': record.pre_text})
        ));
    }
    if (record.tombstone !== undefined) {
        ACTIONS.ACTIVE = false;
        let time = d.toLocaleTimeString(undefined, {hour12: false});
        box.appendChild(makeElement('div', {
            'innerHTML': `<br /><strong>${time} Action completed.</strong>`
        }))
    }
}