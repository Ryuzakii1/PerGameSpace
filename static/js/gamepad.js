// static/js/gamepad.js

import { updateGamepadStatus } from './ui.js';

let nostalgistInstance = null;

// Standard Gamepad Button Mapping (Common for most controllers)
// Maps RetroArch button IDs to standard gamepad button indices
const gamepadMap = {
    0: 1,  // A Button (RetroPad B) -> Gamepad B
    1: 0,  // B Button (RetroPad Y) -> Gamepad A
    2: 3,  // X Button (RetroPad X) -> Gamepad Y
    3: 2,  // Y Button (RetroPad A) -> Gamepad X
    4: 4,  // L Button (RetroPad L) -> Gamepad L1
    5: 6,  // L2 Button
    6: 5,  // R Button (RetroPad R) -> Gamepad R1
    7: 7,  // R2 Button
    8: 8,  // Select (RetroPad Select)
    9: 9,  // Start (RetroPad Start)
    10: 12, // D-Pad Up
    11: 13, // D-Pad Down
    12: 14, // D-Pad Left
    13: 15, // D-Pad Right
};

// --- Gamepad Detection and Polling ---
window.addEventListener('gamepadconnected', (event) => {
    console.log('Gamepad connected:', event.gamepad.id);
    updateGamepadStatus(`🎮 ${event.gamepad.id}`);
});

window.addEventListener('gamepaddisconnected', (event) => {
    console.log('Gamepad disconnected:', event.gamepad.id);
    updateGamepadStatus('');
});

export function pollGamepads() {
    if (!nostalgistInstance) return;

    const gamepads = navigator.getGamepads();
    if (gamepads[0]) {
        const gp = gamepads[0];

        // Handle Buttons
        for (const retroarchId in gamepadMap) {
            const gamepadIndex = gamepadMap[retroarchId];
            if (gp.buttons[gamepadIndex]) {
                const pressed = gp.buttons[gamepadIndex].pressed;
                // RetroArch IDs for SNES buttons are slightly different
                // We map them here for simplicity
                const snesMap = { 0:0, 1:1, 2:2, 3:3, 4:4, 6:5, 8:8, 9:9 };
                if (snesMap[retroarchId] !== undefined) {
                     nostalgistInstance.setButton(0, 0, snesMap[retroarchId], pressed);
                }
            }
        }
        
        // Handle D-Pad (as buttons)
        nostalgistInstance.setButton(0, 0, 5, gp.buttons[12].pressed); // Up
        nostalgistInstance.setButton(0, 0, 6, gp.buttons[13].pressed); // Down
        nostalgistInstance.setButton(0, 0, 7, gp.buttons[14].pressed); // Left
        nostalgistInstance.setButton(0, 0, 8, gp.buttons[15].pressed); // Right

        // Handle Analog Stick as D-Pad
        const threshold = 0.5;
        nostalgistInstance.setButton(0, 0, 5, gp.axes[1] < -threshold); // Up
        nostalgistInstance.setButton(0, 0, 6, gp.axes[1] > threshold);  // Down
        nostalgistInstance.setButton(0, 0, 7, gp.axes[0] < -threshold); // Left
        nostalgistInstance.setButton(0, 0, 8, gp.axes[0] > threshold);  // Right
    }
}

// --- Initialization ---
export function initializeGamepad(nostalgist) {
    if (nostalgist) {
        nostalgistInstance = nostalgist;
    }
    // Check for already connected gamepads
    const gamepads = navigator.getGamepads();
    if (gamepads[0]) {
        updateGamepadStatus(`🎮 ${gamepads[0].id}`);
    }
}
