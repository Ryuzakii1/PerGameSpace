// Function to display a toast notification
function showToast(message, category = 'info', duration = 5000) {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        console.error('Toast container not found with ID "toast-container"!');
        return;
    }

    const toast = document.createElement('div');
    toast.className = `toast ${category}`;
    toast.innerHTML = `
        <span class="toast-message">${message}</span>
        <button class="toast-close-btn">&times;</button>
    `;

    // Set CSS variable for progress bar animation duration
    toast.style.setProperty('--toast-duration', `${duration / 1000}s`);
    toast.classList.add('has-progress-bar'); // Enable progress bar animation

    toastContainer.appendChild(toast);

    // Trigger reflow to ensure CSS transition starts from initial state
    void toast.offsetWidth;

    // Add 'show' class to start the entrance animation
    toast.classList.add('show');

    // Auto-hide the toast after the specified duration
    const timeoutId = setTimeout(() => {
        hideToast(toast);
    }, duration);

    // Add event listener for the manual close button
    toast.querySelector('.toast-close-btn').addEventListener('click', () => {
        clearTimeout(timeoutId); // Stop the auto-dismiss timer
        hideToast(toast); // Immediately hide
    });
}

// Function to hide a toast and remove it from the DOM after transition
function hideToast(toastElement) {
    toastElement.classList.remove('show');
    toastElement.classList.add('fade-out'); // Trigger the fade-out animation

    // Remove the toast from the DOM after its transition completes
    toastElement.addEventListener('transitionend', () => {
        if (!toastElement.classList.contains('show')) { // Ensure it's truly hidden before removing
            toastElement.remove();
        }
    }, { once: true }); // Use { once: true } to ensure listener is removed after first use
}


// --- Logic to Process Flask's Flashed Messages on Page Load ---
document.addEventListener('DOMContentLoaded', () => {
    const flashedMessagesData = document.getElementById('flashed-messages-data');
    if (flashedMessagesData) {
        const messages = flashedMessagesData.querySelectorAll('span[data-category]');
        messages.forEach(span => {
            const category = span.dataset.category;
            const message = span.dataset.message;
            // Display each flashed message as a toast
            showToast(message, category);
        });
        // Clear the hidden div after processing to prevent re-display on subsequent partial page loads
        flashedMessagesData.innerHTML = '';
    }
});