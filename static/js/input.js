// static/js/input.js

let nostalgistInstance = null;
let isKeyBindingMode = false;

// --- DOM Element References ---
const elements = {
    keyBindingsList: document.getElementById('keyBindingsList'),
    saveBindingsButton: document.getElementById('saveBindingsButton'),
    resetBindingsButton: document.getElementById('resetBindingsButton'),
    settingsPanel: document.getElementById('settingsPanel'),
    settingsButton: document.getElementById('settingsButton'),
};

// --- Default & Current Key Maps ---
const defaultKeyMap = {
    'Left': { key: 'ArrowLeft', port: 0, index: 0, id: 7 },
    'Right': { key: 'ArrowRight', port: 0, index: 0, id: 8 },
    'Up': { key: 'ArrowUp', port: 0, index: 0, id: 5 },
    'Down': { key: 'ArrowDown', port: 0, index: 0, id: 6 },
    'A Button': { key: 'z', port: 0, index: 0, id: 0 },
    'B Button': { key: 'x', port: 0, index: 0, id: 1 },
    'X Button': { key: 'a', port: 0, index: 0, id: 2 },
    'Y Button': { key: 's', port: 0, index: 0, id: 3 },
    'L Button': { key: 'd', port: 0, index: 0, id: 4 },
    'R Button': { key: 'c', port: 0, index: 0, id: 9 },
    'Start': { key: 'Enter', port: 0, index: 0, id: 10 },
    'Select': { key: 'Shift', port: 0, index: 0, id: 11 },
};
let currentKeyMap = {};
let reverseKeyMap = {};

// --- Core Input Functions ---
export function getCurrentKeyMap() {
    return currentKeyMap;
}

function updateReverseKeyMap() {
    reverseKeyMap = {};
    for (const controlName in currentKeyMap) {
        const binding = currentKeyMap[controlName];
        if (binding?.key) {
            reverseKeyMap[binding.key] = binding;
        }
    }
}

function loadKeyBindings() {
    const savedBindings = localStorage.getItem('emulatorKeyBindings');
    if (savedBindings) {
        try {
            currentKeyMap = JSON.parse(savedBindings);
        } catch (e) {
            currentKeyMap = { ...defaultKeyMap };
        }
    } else {
        currentKeyMap = { ...defaultKeyMap };
    }
    updateReverseKeyMap();
}

function saveKeyBindings() {
    localStorage.setItem('emulatorKeyBindings', JSON.stringify(currentKeyMap));
    updateReverseKeyMap();
    if (nostalgistInstance) {
        nostalgistInstance.setKeymap(currentKeyMap);
    }
    alert('Key bindings saved!');
}

function resetKeyBindings() {
    currentKeyMap = { ...defaultKeyMap };
    saveKeyBindings();
    renderKeyBindings();
}

function renderKeyBindings() {
    if (!elements.keyBindingsList) return;
    elements.keyBindingsList.innerHTML = '';
    for (const controlName in defaultKeyMap) {
        const bindingInfo = currentKeyMap[controlName] || defaultKeyMap[controlName];
        const item = document.createElement('div');
        item.className = 'key-binding-item';
        item.innerHTML = `
            <span class="control-name">${controlName}:</span>
            <button class="key-bind-button" data-control="${controlName}">${bindingInfo.key}</button>
        `;
        elements.keyBindingsList.appendChild(item);
    }
    elements.keyBindingsList.querySelectorAll('.key-bind-button').forEach(button => {
        button.addEventListener('click', (e) => startKeyBindingMode(e.target));
    });
}

function startKeyBindingMode(buttonElement) {
    if (isKeyBindingMode) return;
    isKeyBindingMode = true;
    const originalText = buttonElement.textContent;
    buttonElement.textContent = 'Press a key...';
    buttonElement.classList.add('active-binding');

    const handleKeyPress = (event) => {
        event.preventDefault();
        event.stopPropagation();
        const controlName = buttonElement.dataset.control;
        currentKeyMap[controlName].key = event.key;
        buttonElement.textContent = event.key;
        endKeyBindingMode(buttonElement);
    };

    const endKeyBindingMode = (btn) => {
        isKeyBindingMode = false;
        btn.classList.remove('active-binding');
        document.removeEventListener('keydown', handleKeyPress, true);
    };

    document.addEventListener('keydown', handleKeyPress, { once: true, capture: true });
}

// --- Event Listeners ---
function setupEventListeners() {
    document.addEventListener('keydown', (event) => {
        if (isKeyBindingMode) return;
        const boundControl = reverseKeyMap[event.key];
        if (nostalgistInstance && boundControl) {
            nostalgistInstance.setButton(boundControl.port, boundControl.index, boundControl.id, true);
        }
    });

    document.addEventListener('keyup', (event) => {
        if (isKeyBindingMode) return;
        const boundControl = reverseKeyMap[event.key];
        if (nostalgistInstance && boundControl) {
            nostalgistInstance.setButton(boundControl.port, boundControl.index, boundControl.id, false);
        }
    });

    elements.saveBindingsButton?.addEventListener('click', saveKeyBindings);
    elements.resetBindingsButton?.addEventListener('click', resetKeyBindings);
    elements.settingsButton?.addEventListener('click', () => {
        if (elements.settingsPanel?.classList.contains('open')) {
            renderKeyBindings();
        }
    });
}

// --- Initialization ---
export function initializeInput(nostalgist) {
    if (nostalgist) {
        nostalgistInstance = nostalgist;
    }
    loadKeyBindings();
    
    if (!elements.saveBindingsButton.dataset.initialized) {
        setupEventListeners();
        elements.saveBindingsButton.dataset.initialized = 'true';
    }
}
