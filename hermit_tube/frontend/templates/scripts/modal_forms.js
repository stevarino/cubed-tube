function showSettings(e) {
    e.preventDefault();
    e.stopPropagation();
    closeMenus();
    let container = showModal(hideSettings);
    container.classList.add('form');
    let form = document.getElementById('form')
    form.appendChild(makeElement('h2', {innerText: 'Settings'}));

    let checkboxes = [
        ['Embedded Player', 'player'],
        ['Autoplay Next Video', 'autoplay'],
        ['Fullscreen', 'use_fullscreen'],
    ];

    for (const [label, key] of checkboxes) {
        let checkbox = {
            type: 'checkbox',
            id: `option_${key}`,
            name: `option_${key}`,
            change: (e) => {
                SETTINGS[key] = e.target.checked;
                saveSettings();
            }
        }
        if (SETTINGS[key]) {
            checkbox.checked = 'checked';
        }

        form.appendChild(makeElement(
            'label', {for: `option_${key}`},
            makeElement('span', {innerText: label}),
            makeElement('input', checkbox)
        ));
    }

    form.appendChild(makeElement('h2', {innerText: 'Profiles'}));
    for (const profile of listProfiles()) {
        let para = makeElement('p', {});
        let label = makeElement(
            'span', {innerText: profile.profile, class: 'label'}
        )
        form.appendChild(para);
        para.appendChild(label);
        para.appendChild(makeElement('span', {
            class: 'material-icons rename_profile', 
            innerText: 'edit',
            click: (e) => {
                renameProfile(profile)
                label.innerText = profile.profile;
            }
        }));
        para.appendChild(makeElement('span', {
            class: 'material-icons delete_profile', 
            innerText: 'delete',
            click: (e) => {
                deleteProfile(profile);
                para.parentElement.removeChild(para);
            }
        }));
    }
}

function hideSettings() {
    document.getElementById('form').innerHTML = '';
}