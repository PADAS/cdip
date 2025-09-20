// JavaScript for handling Integration Type change warnings
// Tracks state field changes and modifies HTMX requests accordingly

let stateFieldEdited = false;

// Track when the state field is edited
function trackStateChanges() {
    const stateField = document.querySelector('#div_id_state input, #div_id_state textarea, #div_id_state select');
    if (stateField) {
        stateField.addEventListener('input', function() {
            stateFieldEdited = true;
        });
        stateField.addEventListener('change', function() {
            stateFieldEdited = true;
        });
    }
}

// Handle Integration Type changes
document.addEventListener('DOMContentLoaded', function() {
    // Set up state change tracking
    trackStateChanges();
    
    // Re-setup state change tracking after HTMX updates
    document.body.addEventListener('htmx:afterRequest', function(event) {
        if (event.target.id === 'id_type' && event.detail.xhr.status === 200) {
            // Re-setup state change tracking for any new state fields
            trackStateChanges();
        }
    });
});
