// static/js/emulator.js

import { Nostalgist } from '/static/js/nostalgist.js';
import { initializeUI, showLoadingOverlay, hideLoadingOverlay, updateStatus } from './ui.js';
import { initializeInput, getCurrentKeyMap } from './input.js';
import { initializeGamepad, pollGamepads } from './gamepad.js';

// --- Data Retrieval ---
const gameDataEncodedElement = document.getElementById('game-data-encoded');
if (!gameDataEncodedElement) throw new Error("Missing game data element.");

const encodedGameDetails = gameDataEncodedElement.dataset.encodedDetails;
if (!encodedGameDetails) throw new Error("Missing encoded game details.");

let gameDetails = {};
try {
    gameDetails = JSON.parse(atob(encodedGameDetails));
} catch (e) {
    throw new Error("Corrupted game data.");
}

const { rom_url: romUrl, title: gameTitle, emulator_core: emulatorCore, emulator_aspect_ratio: emulatorAspectRatioStr } = gameDetails;
let nostalgist = null;

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


// --- Main Emulator Initialization ---
async function initializeEmulator() {
    console.log("DEBUG: initializeEmulator called.");
    showLoadingOverlay('Initializing emulator...', 'Please wait while the emulator loads.');

    if (!romUrl || !emulatorCore) {
        showLoadingOverlay('Error: ROM or Core is missing.', 'Please check settings and console.');
        return;
    }

    try {
        const nostalgistConfig = {
            element: document.getElementById('snes-canvas'),
            core: {
                name: emulatorCore,
                js: `/static/js/cores/${emulatorCore}_libretro.js`,
                wasm: `/static/js/cores/${emulatorCore}_libretro.wasm`,
            },
            rom: romUrl,
            audio: true,
            keymap: getCurrentKeyMap(),
            onLoad: () => updateStatus(`Game "${gameTitle}" loaded.`),
            onRun: () => {
                console.log("DEBUG: Nostalgist onRun callback fired. Hiding overlay.");
                hideLoadingOverlay();
                gameLoop(); // Start the gamepad polling loop
            },
            onError: (error) => {
                console.error("Nostalgist.js Error:", error);
                showLoadingOverlay(`Error: ${error.message || error}.`, 'Check console for details.');
            }
        };

        nostalgist = await Nostalgist.launch(nostalgistConfig);
        updateStatus('Emulator initialized. Loading ROM...');
        
        // Make nostalgist instance available to other modules
        initializeUI(nostalgist, initializeEmulator, aspectRatio);
        initializeInput(nostalgist);
        initializeGamepad(nostalgist);

    } catch (error) {
        console.error("Failed to initialize Nostalgist.js:", error);
        showLoadingOverlay(`Failed to initialize: ${error.message || error}.`, 'Check console for details.');
    }
}

// --- Game Loop for Gamepad Polling ---
function gameLoop() {
    if (nostalgist) {
        pollGamepads(nostalgist);
        requestAnimationFrame(gameLoop);
    }
}

// --- Initial Setup ---
window.addEventListener('load', () => {
    // --- FIX: Pass the calculated aspect ratio to the UI module on initial load ---
    initializeUI(null, initializeEmulator, aspectRatio); 
    initializeInput(null);

    // Attach the main click listener to start everything
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
        loadingOverlay.addEventListener('click', () => {
            initializeEmulator();
            
            console.log("DEBUG: Starting 3-second failsafe timer to hide loading overlay.");
            setTimeout(() => {
                console.log("DEBUG: Failsafe timer finished. Forcibly hiding overlay.");
                hideLoadingOverlay();
            }, 3000); 

        }, { once: true });
    }
});
