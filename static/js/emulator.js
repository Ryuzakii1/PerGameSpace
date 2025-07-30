// static/js/emulator.js

// Import Nostalgist.js from your local static/js folder
import { Nostalgist } from '/static/js/nostalgist.js';

// --- Data Retrieval from HTML (Passed by Flask) ---
const gameDataEncodedElement = document.getElementById('game-data-encoded');

if (!gameDataEncodedElement) {
    console.error("Error: 'game-data-encoded' element not found. Cannot retrieve game details.");
    document.body.innerHTML = '<div class="flex flex-col items-center justify-center min-h-screen text-red-400 bg-gray-900">Error: Game data not found. Please try again or contact support.</div>';
    throw new Error("Missing game data element."); // Stop execution
}

const encodedGameDetails = gameDataEncodedElement.dataset.encodedDetails;

if (!encodedGameDetails) {
    console.error("Error: 'data-encoded-details' attribute is missing from 'game-data-encoded' element.");
    document.body.innerHTML = '<div class="flex flex-col items-center justify-center min-h-screen text-red-400 bg-gray-900">Error: Incomplete game data. Please try again or contact support.</div>';
    throw new Error("Missing encoded game details."); // Stop execution
}

let gameDetails = {};
try {
    const decodedGameDetails = atob(encodedGameDetails);
    gameDetails = JSON.parse(decodedGameDetails);
} catch (e) {
    console.error("Error decoding or parsing game details:", e);
    document.body.innerHTML = '<div class="flex flex-col items-center justify-center min-h-screen text-red-400 bg-gray-900">Error: Corrupted game data. Please try again or contact support.</div>';
    throw new Error("Corrupted game data."); // Stop execution
}

// Extract variables from the parsed gameDetails object
const romUrl = gameDetails.rom_url;
const gameTitle = gameDetails.title;
const systemName = gameDetails.system;
const emulatorCore = gameDetails.emulator_core;
const emulatorAspectRatioStr = gameDetails.emulator_aspect_ratio; // e.g., "4/3" or "10/9"

// Parse the aspect ratio string into a numerical value (e.g., "4/3" becomes 1.333)
let aspectRatio = 4 / 3; // Default to 4:3 in case of parsing error
try {
    const parts = emulatorAspectRatioStr.split('/');
    if (parts.length === 2) {
        const num = parseFloat(parts[0]);
        const den = parseFloat(parts[1]);
        if (!isNaN(num) && !isNaN(den) && den !== 0) {
            aspectRatio = num / den;
        }
    }
} catch (e) {
    console.error("Error parsing aspect ratio:", e);
}

// --- DEBUGGING LOGS ---
console.log("DEBUG: romUrl received from Flask:", romUrl);
console.log("DEBUG: game object details:", gameDetails);
console.log("DEBUG: emulatorCore received:", emulatorCore);
console.log("DEBUG: emulatorAspectRatio (parsed):", aspectRatio);
// --- END DEBUGGING LOGS ---

// Get references to HTML elements
const canvas = document.getElementById('snes-canvas');
const loadingOverlay = document.getElementById('loading-overlay');
const loadingMessage = document.getElementById('loading-message');
const loadingSubMessage = document.getElementById('loading-sub-message'); // New sub-message element
const statusMessageDiv = document.getElementById('statusMessage');
const playPauseButton = document.getElementById('playPauseButton');
const resetButton = document.getElementById('resetButton');
const saveStateButton = document.getElementById('saveStateButton');
const loadStateButton = document.getElementById('loadStateButton');
const fullscreenButton = document.getElementById('fullscreenButton');
const settingsButton = document.getElementById('settingsButton'); // New settings button
const emulatorScreen = document.getElementById('emulator-screen');

// Settings Panel elements (Updated IDs and class)
const settingsPanel = document.getElementById('settingsPanel');
const closeSettingsPanelButton = document.getElementById('closeSettingsPanel');
const keyBindingsList = document.getElementById('keyBindingsList');
const saveBindingsButton = document.getElementById('saveBindingsButton');
const resetBindingsButton = document.getElementById('resetBindingsButton');

let nostalgist = null;
let isPaused = false;
let savedState = null;
let isKeyBindingMode = false; // Flag to indicate if we are in key binding mode

// --- Default Key Map for SNES (Nostalgist.js uses RetroArch button IDs) ---
// These are common RetroArch button IDs for gamepad 1
const defaultKeyMap = {
    'Left': { key: 'ArrowLeft', port: 0, index: 0, id: 7 },
    'Right': { key: 'ArrowRight', port: 0, index: 0, id: 8 },
    'Up': { key: 'ArrowUp', port: 0, index: 0, id: 5 },
    'Down': { key: 'ArrowDown', port: 0, index: 0, id: 6 },
    'A Button': { key: 'z', port: 0, index: 0, id: 0 }, // RetroPad B (SNES A)
    'B Button': { key: 'x', port: 0, index: 0, id: 1 }, // RetroPad Y (SNES B)
    'X Button': { key: 'a', port: 0, index: 0, id: 2 }, // RetroPad X (SNES X)
    'Y Button': { key: 's', port: 0, index: 0, id: 3 }, // RetroPad A (SNES Y)
    'L Button': { key: 'd', port: 0, index: 0, id: 4 }, // RetroPad L
    'R Button': { key: 'c', port: 0, index: 0, id: 9 }, // RetroPad R
    'Start': { key: 'Enter', port: 0, index: 0, id: 10 }, // RetroPad Start
    'Select': { key: 'Shift', port: 0, index: 0, id: 11 }, // RetroPad Select
};

let currentKeyMap = {}; // This will hold the active key bindings

/**
 * Updates the status message displayed on the page.
 * @param {string} message - The message to display.
 * @param {string} type - The type of message ('info' or 'error') for styling.
 */
function updateStatus(message, type = 'info') {
    if (statusMessageDiv) {
        statusMessageDiv.textContent = message;
        statusMessageDiv.className = `status-message mt-4 text-sm ${type === 'error' ? 'text-red-400' : 'text-gray-300'}`;
    } else {
        console.warn("Status message div not found. Message:", message);
    }
}

/**
 * Hides the loading overlay.
 */
function hideLoadingOverlay() {
    if (loadingOverlay) {
        loadingOverlay.style.display = 'none';
        console.log("DEBUG: Loading overlay hidden via direct style manipulation.");
    }
}

/**
 * Shows the loading overlay with an optional message.
 * @param {string} message - The main message to display.
 * @param {string} subMessage - An optional secondary message.
 */
function showLoadingOverlay(message = 'Click to start the game', subMessage = '') {
    if (loadingMessage && loadingOverlay) {
        loadingMessage.textContent = message;
        if (subMessage && loadingSubMessage) {
            loadingSubMessage.textContent = subMessage;
            loadingSubMessage.classList.remove('hidden');
        } else if (loadingSubMessage) {
            loadingSubMessage.classList.add('hidden');
        }
        loadingOverlay.style.display = 'flex';
        console.log("DEBUG: Loading overlay shown with message:", message);
    }
}

/**
 * Resizes the canvas element to match its parent container's dimensions
 * while maintaining the dynamically determined aspect ratio.
 * This function is called by the ResizeObserver.
 */
function updateCanvasDimensions() {
    if (!emulatorScreen || !canvas) {
        console.warn('emulatorScreen or canvas not found, skipping canvas resize.');
        return;
    }

    if (emulatorScreen.clientWidth === 0 || emulatorScreen.clientHeight === 0) {
        console.warn('emulatorScreen has zero dimensions, skipping canvas resize.');
        return;
    }

    const parentWidth = emulatorScreen.clientWidth;
    const parentHeight = emulatorScreen.clientHeight;

    let newWidth = parentWidth;
    let newHeight = parentWidth / aspectRatio;

    if (newHeight > parentHeight) {
        newHeight = parentHeight;
        newWidth = parentHeight * aspectRatio;
    }

    canvas.width = newWidth;
    canvas.height = newHeight;

    console.log('DEBUG: Canvas attributes updated to:', canvas.width, 'x', canvas.height);
}

/**
 * Applies the current key bindings to the Nostalgist emulator.
 */
async function applyKeyBindingsToEmulator() {
    if (!nostalgist) {
        console.warn("Nostalgist instance not available to apply key bindings.");
        return;
    }
    try {
        await nostalgist.setKeymap(currentKeyMap);
        console.log("DEBUG: Key bindings applied to emulator.");
    } catch (error) {
        console.error("Error applying key bindings to emulator:", error);
    }
}

/**
 * Initializes and launches the Nostalgist.js emulator.
 */
async function initializeEmulator() {
    console.log("DEBUG: initializeEmulator called.");
    showLoadingOverlay('Initializing emulator...', 'Please wait while the emulator loads.');

    if (!romUrl || !emulatorCore || !canvas) {
        const errorMessage = !romUrl ? 'ROM URL is missing.' : !emulatorCore ? 'Emulator core is not configured.' : 'Emulator canvas not found.';
        showLoadingOverlay(`Error: ${errorMessage}`, 'Please check settings and console for details.');
        console.error('Initialization Error:', errorMessage);
        return;
    }

    try {
        const nostalgistConfig = {
            element: canvas,
            core: {
                name: emulatorCore,
                js: `/static/js/cores/${emulatorCore}_libretro.js`,
                wasm: `/static/js/cores/${emulatorCore}_libretro.wasm`,
            },
            rom: romUrl,
            audio: true,
            keymap: currentKeyMap,
            retroarchConfig: {
                rewind_enable: true,
                savestate_auto_save: true,
                savestate_auto_load: true,
            },
            onLoad: () => {
                updateStatus(`Game "${gameTitle}" loaded.`);
                isPaused = false;
                if (playPauseButton) playPauseButton.textContent = 'Pause';
            },
            onRun: () => {
                console.log("DEBUG: Nostalgist onRun callback fired. Hiding overlay.");
                hideLoadingOverlay();
            },
            onPause: () => {
                updateStatus('Game paused.');
                isPaused = true;
                if (playPauseButton) playPauseButton.textContent = 'Play';
            },
            onResume: () => {
                updateStatus('Game resumed.');
                isPaused = false;
                if (playPauseButton) playPauseButton.textContent = 'Pause';
            },
            onError: (error) => {
                console.error("Nostalgist.js Error:", error);
                showLoadingOverlay(`Error loading emulator: ${error.message || error}.`, 'Please check the browser console for more details (F12).');
            }
        };

        console.log("DEBUG: Nostalgist.launch config:", nostalgistConfig);
        nostalgist = await Nostalgist.launch(nostalgistConfig);
        updateStatus('Emulator initialized. Loading ROM...');

    } catch (error) {
        console.error("Failed to initialize Nostalgist.js:", error);
        showLoadingOverlay(`Failed to initialize emulator: ${error.message || error}.`, 'This might be due to an invalid ROM, unsupported core, or network issues. Check console for details.');
    }
}

// --- Key Binding Functions ---

function loadKeyBindings() {
    const savedBindings = localStorage.getItem('emulatorKeyBindings');
    if (savedBindings) {
        try {
            currentKeyMap = JSON.parse(savedBindings);
            console.log("DEBUG: Loaded key bindings from localStorage:", currentKeyMap);
        } catch (e) {
            console.error("Error parsing saved key bindings, using defaults:", e);
            currentKeyMap = { ...defaultKeyMap };
        }
    } else {
        currentKeyMap = { ...defaultKeyMap };
        console.log("DEBUG: No saved key bindings found, using defaults.");
    }
}

function saveKeyBindings() {
    localStorage.setItem('emulatorKeyBindings', JSON.stringify(currentKeyMap));
    updateStatus('Key bindings saved successfully!', 'info');
    updateReverseKeyMap();
}

function resetKeyBindings() {
    currentKeyMap = { ...defaultKeyMap };
    saveKeyBindings();
    renderKeyBindings();
    updateStatus('Key bindings reset to defaults.', 'info');
}

function renderKeyBindings() {
    if (!keyBindingsList) return;
    keyBindingsList.innerHTML = '';
    for (const controlName in defaultKeyMap) {
        const bindingInfo = currentKeyMap[controlName] || defaultKeyMap[controlName];
        const bindingItem = document.createElement('div');
        bindingItem.className = 'key-binding-item flex justify-between items-center py-2 border-b border-gray-700 last:border-b-0';
        bindingItem.innerHTML = `
            <span class="control-name text-gray-300">${controlName}:</span>
            <button class="key-bind-button px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition-colors duration-200" data-control="${controlName}">${bindingInfo.key}</button>
        `;
        keyBindingsList.appendChild(bindingItem);
    }
    document.querySelectorAll('.key-bind-button').forEach(button => {
        button.addEventListener('click', (event) => startKeyBindingMode(event.target));
    });
}

let currentKeyBindingCancelListeners = [];

function startKeyBindingMode(buttonElement) {
    if (isKeyBindingMode) return;
    isKeyBindingMode = true;
    const originalText = buttonElement.textContent;
    buttonElement.textContent = 'Press a key...';
    buttonElement.classList.add('active-binding');
    updateStatus('Press any key to set the new binding for ' + buttonElement.dataset.control, 'info');

    const handleKeyPress = (event) => {
        event.preventDefault();
        event.stopPropagation();
        const controlName = buttonElement.dataset.control;
        const newKey = event.key;
        if (currentKeyMap[controlName]) {
            currentKeyMap[controlName].key = newKey;
        }
        buttonElement.textContent = newKey;
        buttonElement.classList.remove('active-binding');
        updateStatus(`Key for ${controlName} set to: ${newKey}`, 'info');
        endKeyBindingMode();
    };

    const handleClickOutside = (event) => {
        if (!buttonElement.contains(event.target) && isKeyBindingMode) {
            buttonElement.textContent = originalText;
            buttonElement.classList.remove('active-binding');
            updateStatus('Key binding cancelled.', 'warning');
            endKeyBindingMode();
        }
    };

    currentKeyBindingCancelListeners = [
        { type: 'keydown', handler: handleKeyPress, capture: true },
        { type: 'click', handler: handleClickOutside, capture: true }
    ];

    document.addEventListener('keydown', handleKeyPress, true);
    document.addEventListener('click', handleClickOutside, true);
}

function endKeyBindingMode() {
    isKeyBindingMode = false;
    currentKeyBindingCancelListeners.forEach(({ type, handler, capture }) => {
        document.removeEventListener(type, handler, capture);
    });
    currentKeyBindingCancelListeners = [];
}

// --- Control Event Listeners ---
if (playPauseButton) {
    playPauseButton.addEventListener('click', () => {
        if (!nostalgist) return;
        isPaused ? nostalgist.resume() : nostalgist.pause();
    });
}

if (resetButton) {
    resetButton.addEventListener('click', () => {
        if (!nostalgist) return;
        updateStatus('Resetting game...');
        nostalgist.exit().then(() => initializeEmulator());
    });
}

if (saveStateButton) {
    saveStateButton.addEventListener('click', async () => {
        if (!nostalgist) return;
        try {
            updateStatus('Saving state...');
            const { state } = await nostalgist.saveState();
            savedState = state;
            updateStatus('Game state saved successfully!');
        } catch (error) {
            updateStatus(`Error saving state: ${error.message}`, 'error');
        }
    });
}

if (loadStateButton) {
    loadStateButton.addEventListener('click', async () => {
        if (!nostalgist || !savedState) {
            updateStatus(nostalgist ? 'No saved state found to load.' : 'Emulator not loaded yet.', 'warning');
            return;
        }
        try {
            updateStatus('Loading state...');
            await nostalgist.loadState(savedState);
            updateStatus('Game state loaded successfully!');
            if (isPaused) nostalgist.resume();
        } catch (error) {
            updateStatus(`Error loading state: ${error.message}`, 'error');
        }
    });
}

if (fullscreenButton) {
    fullscreenButton.addEventListener('click', () => {
        const elem = document.querySelector('.emulator-container');
        if (!document.fullscreenElement) {
            console.log("DEBUG: Fullscreen button clicked. Requesting fullscreen.");
            elem.requestFullscreen().catch(err => {
                updateStatus(`Error attempting to enable full-screen mode: ${err.message} (${err.name})`, 'error');
                console.error(`Fullscreen Error: ${err.message} (${err.name})`);
            });
        } else {
            console.log("DEBUG: Fullscreen button clicked. Exiting fullscreen.");
            document.exitFullscreen();
        }
    });
}

// --- Settings Panel Event Listeners ---
if (settingsButton && settingsPanel) {
    settingsButton.addEventListener('click', () => {
        settingsPanel.classList.toggle('open');
        console.log("DEBUG: Settings button clicked. Panel open state:", settingsPanel.classList.contains('open'));
        if (settingsPanel.classList.contains('open')) {
            renderKeyBindings();
        } else {
            if (isKeyBindingMode) {
                endKeyBindingMode();
                renderKeyBindings();
            }
        }
    });
}

if (closeSettingsPanelButton && settingsPanel) {
    closeSettingsPanelButton.addEventListener('click', () => {
        settingsPanel.classList.remove('open');
        console.log("DEBUG: Close Settings button clicked.");
        if (isKeyBindingMode) {
            endKeyBindingMode();
            renderKeyBindings();
        }
    });
}

if (saveBindingsButton) {
    saveBindingsButton.addEventListener('click', saveKeyBindings);
}
if (resetBindingsButton) {
    resetBindingsButton.addEventListener('click', resetKeyBindings);
}


// --- Keyboard Input Handling (Modified to use currentKeyMap) ---
let reverseKeyMap = {};
function updateReverseKeyMap() {
    reverseKeyMap = {};
    for (const controlName in currentKeyMap) {
        const binding = currentKeyMap[controlName];
        if (binding && binding.key) {
            reverseKeyMap[binding.key] = binding;
        }
    }
    console.log("DEBUG: Updated reverse key map:", reverseKeyMap);
}

// These functions need to be defined outside the event listener to be accessible for removal
let handleEmulatorKeyPress = (event) => {
    if (isKeyBindingMode) return;

    // Prevent default browser actions for common emulator keys
    if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(event.key)) {
        event.preventDefault();
    }

    const boundControl = reverseKeyMap[event.key];
    if (nostalgist && boundControl) {
        const { port, index, id } = boundControl;
        nostalgist.setButton(port, index, id, true);
    }
};

let handleEmulatorKeyUp = (event) => {
    if (isKeyBindingMode) return;

    const boundControl = reverseKeyMap[event.key];
    if (nostalgist && boundControl) {
        const { port, index, id } = boundControl;
        nostalgist.setButton(port, index, id, false);
    }
};

document.addEventListener('keydown', handleEmulatorKeyPress);
document.addEventListener('keyup', handleEmulatorKeyUp);


// Use ResizeObserver for more robust canvas resizing
const resizeObserver = new ResizeObserver(entries => {
    for (let entry of entries) {
        if (entry.target === emulatorScreen) {
            updateCanvasDimensions();
        }
    }
});

// Initialize the emulator and observer when the entire page has loaded
window.addEventListener('load', () => {
    console.log("DEBUG: Window loaded event fired.");
    if (emulatorScreen) {
        resizeObserver.observe(emulatorScreen);
        updateCanvasDimensions();
    } else {
        console.error("Emulator screen element not found. ResizeObserver will not be attached.");
    }

    loadKeyBindings(); // Load key bindings on page load
    updateReverseKeyMap(); // Initialize reverse map based on loaded bindings
    showLoadingOverlay(); // Show the "Click to start" message

    // Attach click listener to loading overlay only after page load
    if (loadingOverlay) {
        console.log("DEBUG: Attaching click listener to loading overlay.");
        loadingOverlay.addEventListener('click', () => {
            console.log("DEBUG: Loading overlay clicked.");
            if (!nostalgist) { // Only initialize if nostalgist is not already loaded
                initializeEmulator();

                // --- NEW: Add a failsafe timer to hide the overlay ---
                // This is a temporary workaround. If the emulator core fails to load,
                // the `onLoad` event won't fire. This timer will hide the overlay
                // after 5 seconds regardless, allowing us to see any errors on the canvas.
                console.log("DEBUG: Starting 3-second failsafe timer to hide loading overlay.");
                setTimeout(() => {
                    console.log("DEBUG: Failsafe timer finished. Hiding overlay.");
                    hideLoadingOverlay();
                }, 3000); // 3000 milliseconds = 3 seconds
                
            } else {
                console.log("DEBUG: Nostalgist already initialized, ignoring click.");
            }
        }, { once: true }); // Use { once: true } to ensure it only fires once
    } else {
        console.error("Loading overlay element not found. Emulator cannot be started by click.");
        // If loading overlay is missing, auto-start the emulator for debugging
        initializeEmulator();
    }
});
