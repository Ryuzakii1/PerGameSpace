// static/js/ui.js

let nostalgistInstance = null;
let restartEmulatorCallback = null;
let canvasAspectRatio = 4 / 3; // Default aspect ratio

// --- DOM Element References ---
const elements = {
    canvas: document.getElementById('snes-canvas'),
    loadingOverlay: document.getElementById('loading-overlay'),
    loadingMessage: document.getElementById('loading-message'),
    loadingSubMessage: document.getElementById('loading-sub-message'),
    statusMessageDiv: document.getElementById('statusMessage'),
    playPauseButton: document.getElementById('playPauseButton'),
    resetButton: document.getElementById('resetButton'),
    saveStateButton: document.getElementById('saveStateButton'),
    loadStateButton: document.getElementById('loadStateButton'),
    fullscreenButton: document.getElementById('fullscreenButton'),
    settingsButton: document.getElementById('settingsButton'),
    emulatorScreen: document.getElementById('emulator-screen'),
    settingsPanel: document.getElementById('settingsPanel'),
    closeSettingsPanelButton: document.getElementById('closeSettingsPanel'),
    gamepadStatus: document.getElementById('gamepad-status'),
};

let isPaused = false;
let savedState = null;

// --- FIX: Add back the canvas resizing function ---
function updateCanvasDimensions() {
    if (!elements.emulatorScreen || !elements.canvas) return;
    if (elements.emulatorScreen.clientWidth === 0) return;

    const parentWidth = elements.emulatorScreen.clientWidth;
    const parentHeight = elements.emulatorScreen.clientHeight;

    let newWidth = parentWidth;
    let newHeight = parentWidth / canvasAspectRatio;

    if (newHeight > parentHeight) {
        newHeight = parentHeight;
        newWidth = parentHeight * canvasAspectRatio;
    }

    elements.canvas.width = newWidth;
    elements.canvas.height = newHeight;
}


// --- Core UI Functions ---
export function showLoadingOverlay(message = 'Click to start the game', subMessage = '') {
    if (elements.loadingMessage && elements.loadingOverlay) {
        elements.loadingMessage.textContent = message;
        elements.loadingSubMessage.textContent = subMessage;
        elements.loadingOverlay.style.display = 'flex';
    }
}

export function hideLoadingOverlay() {
    if (elements.loadingOverlay) {
        elements.loadingOverlay.style.display = 'none';
    }
}

export function updateStatus(message, type = 'info') {
    if (elements.statusMessageDiv) {
        elements.statusMessageDiv.textContent = message;
        elements.statusMessageDiv.className = `status-message ${type === 'error' ? 'text-red-400' : 'text-gray-300'}`;
    }
}

export function updateGamepadStatus(message) {
    if (elements.gamepadStatus) {
        elements.gamepadStatus.textContent = message;
        elements.gamepadStatus.style.display = message ? 'inline' : 'none';
    }
}

// --- Event Listeners Setup ---
function setupEventListeners() {
    elements.playPauseButton?.addEventListener('click', () => {
        if (!nostalgistInstance) return;
        if (isPaused) {
            nostalgistInstance.resume();
            isPaused = false;
            elements.playPauseButton.textContent = 'Pause';
            updateStatus('Game resumed.');
        } else {
            nostalgistInstance.pause();
            isPaused = true;
            elements.playPauseButton.textContent = 'Play';
            updateStatus('Game paused.');
        }
    });

    elements.resetButton?.addEventListener('click', () => {
        if (!nostalgistInstance) return;
        updateStatus('Resetting game...');
        nostalgistInstance.exit().then(() => restartEmulatorCallback());
    });

    elements.saveStateButton?.addEventListener('click', async () => {
        if (!nostalgistInstance) return;
        try {
            updateStatus('Saving state...');
            const { state } = await nostalgistInstance.saveState();
            savedState = state;
            updateStatus('Game state saved successfully!');
        } catch (error) {
            updateStatus(`Error saving state: ${error.message}`, 'error');
        }
    });

    elements.loadStateButton?.addEventListener('click', async () => {
        if (!nostalgistInstance || !savedState) {
            updateStatus(nostalgistInstance ? 'No saved state found.' : 'Emulator not loaded.', 'warning');
            return;
        }
        try {
            updateStatus('Loading state...');
            await nostalgistInstance.loadState(savedState);
            updateStatus('Game state loaded successfully!');
            if (isPaused) {
                nostalgistInstance.resume();
                isPaused = false;
                elements.playPauseButton.textContent = 'Pause';
            }
        } catch (error) {
            updateStatus(`Error loading state: ${error.message}`, 'error');
        }
    });

    elements.fullscreenButton?.addEventListener('click', () => {
        // --- FIX: Target the emulator screen directly, not the outer container ---
        const elem = elements.emulatorScreen;
        if (!document.fullscreenElement) {
            if (elem?.requestFullscreen) {
                elem.requestFullscreen().catch(err => updateStatus(`Fullscreen error: ${err.message}`, 'error'));
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }
    });

    elements.settingsButton?.addEventListener('click', () => elements.settingsPanel?.classList.toggle('open'));
    elements.closeSettingsPanelButton?.addEventListener('click', () => elements.settingsPanel?.classList.remove('open'));
}

// --- Initialization ---
export function initializeUI(nostalgist, restartCallback, aspectRatio) {
    if (nostalgist) {
        nostalgistInstance = nostalgist;
    }
    if (restartCallback) {
        restartEmulatorCallback = restartCallback;
    }
    if (aspectRatio) {
        canvasAspectRatio = aspectRatio;
    }
    
    // Setup listeners and observer only once
    if (!elements.playPauseButton.dataset.initialized) {
        setupEventListeners();

        // --- FIX: Add back the ResizeObserver to handle canvas sizing ---
        const resizeObserver = new ResizeObserver(() => {
            updateCanvasDimensions();
        });
        if (elements.emulatorScreen) {
            resizeObserver.observe(elements.emulatorScreen);
        }
        
        updateCanvasDimensions(); // Initial call to set size
        
        elements.playPauseButton.dataset.initialized = 'true';
    }
}
