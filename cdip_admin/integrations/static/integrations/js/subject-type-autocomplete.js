/**
 * Subject Type Autocomplete Widget
 * Provides auto-complete functionality for subject type selection with ability to create new ones
 * Version: 1.0
 */

function initSubjectTypeAutocomplete(widgetId, options) {
    const container = document.getElementById(widgetId + '_container');
    const input = document.getElementById(widgetId + '_input');
    const hiddenInput = document.getElementById(widgetId + '_hidden');
    const dropdown = document.getElementById(widgetId + '_dropdown');
    const dropdownMenu = document.getElementById(widgetId + '_dropdown_menu');
    const selectedSection = document.getElementById(widgetId + '_selected');
    const createNewSection = document.getElementById(widgetId + '_create_new');
    
    let allChoices = options.choices || [];
    let currentValue = options.currentValue || '';
    let selectedChoice = null;
    
    // Initialize the widget
    function init() {
        console.log('Subject Type Widget: Initializing...');
        console.log('Subject Type Widget: allChoices =', allChoices);
        console.log('Subject Type Widget: currentValue =', currentValue);
        
        setupEventListeners();
        if (currentValue) {
            // Find and set the current selection
            const choice = allChoices.find(c => c[0] === currentValue);
            if (choice) {
                selectChoice(choice);
            }
        }
        
        console.log('Subject Type Widget: Initialization complete');
    }
    
    // Setup event listeners
    function setupEventListeners() {
        // Input typing for autocomplete
        input.addEventListener('input', handleInput);
        input.addEventListener('focus', () => {
            showDropdown();
            if (dropdownMenu.innerHTML === '') {
                showAllChoices();
            }
        });
        input.addEventListener('blur', hideDropdown);
        
        // Dropdown toggle
        dropdown.addEventListener('click', toggleDropdown);
        
        // Click outside to close dropdown
        document.addEventListener('click', (e) => {
            if (!container.contains(e.target)) {
                hideDropdown();
            }
        });
        
        // Clear selection
        container.addEventListener('click', (e) => {
            if (e.target.closest('.clear-selection')) {
                clearSelection();
            }
        });
        
        // Show create new section
        container.addEventListener('click', (e) => {
            if (e.target.closest('.show-create-new')) {
                // Get the search term from the input field
                const currentSearchTerm = input.value.toLowerCase();
                showCreateNewSection(currentSearchTerm);
            }
        });
        
        // Cancel create new
        container.addEventListener('click', (e) => {
            if (e.target.closest('.cancel-create')) {
                hideCreateNewSection();
            }
        });
        
        // Create new subject type
        container.addEventListener('click', (e) => {
            if (e.target.closest('.create-subject-type')) {
                createNewSubjectType();
            }
        });
        
        // Auto-generate slug from display name
        const displayNameInput = container.querySelector('.new-display-name');
        const valueInput = container.querySelector('.new-value');
        
        if (displayNameInput && valueInput) {
            displayNameInput.addEventListener('input', (e) => {
                const slug = e.target.value.toLowerCase()
                    .replace(/[^a-z0-9\s-]/g, '')
                    .replace(/\s+/g, '_')
                    .replace(/_+/g, '_')
                    .replace(/^_|_$/g, '');
                valueInput.value = slug;
                // Trigger validation after auto-filling
                validateValueField();
            });
            
            // Add validation for the value field
            valueInput.addEventListener('input', validateValueField);
            valueInput.addEventListener('blur', validateValueField);
        }
    }
    
    // Handle input typing
    function handleInput(e) {
        const searchTerm = e.target.value.toLowerCase();
        
        if (searchTerm.length === 0) {
            showAllChoices();
            hideCreateNewSection();
        } else {
            const filteredChoices = allChoices.filter(choice => 
                choice[1].toLowerCase().includes(searchTerm) || 
                choice[2].toLowerCase().includes(searchTerm)
            );
            
            // Always render filtered choices (or empty state)
            renderChoices(filteredChoices);
            
            // Always show create new option when there's a search term
            showCreateNewOption(searchTerm);
        }
        
        showDropdown();
    }
    
    // Show all choices
    function showAllChoices() {
        console.log('Subject Type Widget: showAllChoices called, choices =', allChoices);
        renderChoices(allChoices);
    }
    
    // Render choices in dropdown
    function renderChoices(choices) {
        console.log('Subject Type Widget: renderChoices called with', choices);
        dropdownMenu.innerHTML = '';
        
        if (choices.length === 0) {
            dropdownMenu.innerHTML = '<div class="dropdown-item-text text-muted">No subject types found</div>';
            console.log('Subject Type Widget: No choices to render');
            return;
        }
        
        choices.forEach(choice => {
            const item = document.createElement('div');
            item.className = 'dropdown-item choice-item';
            item.innerHTML = `
                <div>
                    <strong>${choice[1]}</strong>
                    <small class="text-muted d-block">${choice[2]}</small>
                </div>
            `;
            
            item.addEventListener('click', () => {
                selectChoice(choice);
                hideDropdown();
            });
            
            dropdownMenu.appendChild(item);
        });
    }
    
    // Show create new option
    function showCreateNewOption(searchTerm) {
        // Check if a create new item already exists and remove it
        const existingCreateNew = dropdownMenu.querySelector('.show-create-new');
        if (existingCreateNew) {
            existingCreateNew.remove();
        }
        
        const createNewItem = document.createElement('div');
        createNewItem.className = 'dropdown-item show-create-new';
        createNewItem.innerHTML = `
            <div class="text-primary">
                <i class="fas fa-plus"></i> Create new: "${searchTerm}"
            </div>
        `;
        
        createNewItem.addEventListener('click', (e) => {
            e.stopPropagation();
            showCreateNewSection(searchTerm);
            hideDropdown();
        });
        
        dropdownMenu.appendChild(createNewItem);
    }
    
    // Select a choice
    function selectChoice(choice) {
        selectedChoice = choice;
        hiddenInput.value = choice[0];
        input.value = '';
        
        // Show selected section
        selectedSection.querySelector('.selected-name').textContent = choice[1];
        selectedSection.querySelector('.selected-value').textContent = choice[2];
        selectedSection.style.display = 'block';
        
        console.log('Selected subject type:', choice);
    }
    
    // Clear selection
    function clearSelection() {
        selectedChoice = null;
        hiddenInput.value = '';
        input.value = '';
        selectedSection.style.display = 'none';
        console.log('Cleared subject type selection');
    }
    
    // Show dropdown
    function showDropdown() {
        console.log('Subject Type Widget: showDropdown called');
        dropdownMenu.style.display = 'block';
        dropdown.setAttribute('aria-expanded', 'true');
    }
    
    // Hide dropdown
    function hideDropdown() {
        // Delay hiding to allow clicks on dropdown items
        setTimeout(() => {
            dropdownMenu.style.display = 'none';
            dropdown.setAttribute('aria-expanded', 'false');
        }, 150);
    }
    
    // Toggle dropdown
    function toggleDropdown() {
        if (dropdownMenu.style.display === 'block') {
            hideDropdown();
        } else {
            showDropdown();
            if (dropdownMenu.innerHTML === '') {
                showAllChoices();
            }
        }
    }
    
    // Show create new section
    function showCreateNewSection(searchTerm = '') {
        createNewSection.style.display = 'block';
        input.value = '';
        hideDropdown();
        
        // Pre-populate the fields with the search term
        if (searchTerm) {
            const displayNameInput = container.querySelector('.new-display-name');
            const valueInput = container.querySelector('.new-value');
            
            if (displayNameInput) {
                // Convert search term to a more user-friendly display name
                // Handle both underscore-separated slugs and space-separated text
                let displayName;
                if (searchTerm.includes('_') || searchTerm.includes('-')) {
                    // If it contains underscores or hyphens, treat as slug and convert to title case
                    const separator = searchTerm.includes('_') ? '_' : '-';
                    displayName = searchTerm
                        .split(separator)
                        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                        .join(' ');
                } else {
                    // If it's regular text, just capitalize each word
                    displayName = searchTerm
                        .split(' ')
                        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                        .join(' ');
                }
                displayNameInput.value = displayName;
            }
            
            if (valueInput) {
                // Generate a proper slug from the search term
                const slug = searchTerm.toLowerCase()
                    .replace(/[^a-z0-9\s-]/g, '')
                    .replace(/\s+/g, '_')
                    .replace(/_+/g, '_')
                    .replace(/^_|_$/g, '');
                valueInput.value = slug;
            }
        }
        
        // Initial validation
        validateValueField();
    }
    
    // Validate the value field
    function validateValueField() {
        const valueInput = container.querySelector('.new-value');
        const createButton = container.querySelector('.create-subject-type');
        const validationMessage = container.querySelector('.validation-message');
        
        if (!valueInput || !createButton) return;
        
        const value = valueInput.value.trim();
        const isValid = isValidValue(value);
        
        // Update button state
        createButton.disabled = !isValid;
        
        // Update visual feedback
        if (value.length === 0) {
            // Empty field - neutral state
            valueInput.classList.remove('is-valid', 'is-invalid');
            if (validationMessage) {
                validationMessage.style.display = 'none';
            }
        } else if (isValid) {
            // Valid field
            valueInput.classList.remove('is-invalid');
            valueInput.classList.add('is-valid');
            if (validationMessage) {
                validationMessage.style.display = 'none';
            }
        } else {
            // Invalid field
            valueInput.classList.remove('is-valid');
            valueInput.classList.add('is-invalid');
            if (validationMessage) {
                validationMessage.style.display = 'block';
                validationMessage.textContent = getValidationMessage(value);
            }
        }
    }
    
    // Check if value is valid
    function isValidValue(value) {
        if (!value || value.length === 0) {
            return false;
        }
        
        // Check length (up to 32 characters)
        if (value.length > 32) {
            return false;
        }
        
        // Check characters (lowercase letters, digits, underscores, and hyphens)
        const validPattern = /^[a-z0-9_-]+$/;
        return validPattern.test(value);
    }
    
    // Get validation error message
    function getValidationMessage(value) {
        if (value.length > 32) {
            return 'Value must be 32 characters or less';
        }
        
        const invalidChars = value.match(/[^a-z0-9_-]/g);
        if (invalidChars) {
            return `Invalid characters: ${invalidChars.join(', ')}. Only lowercase letters, digits, underscores, and hyphens are allowed.`;
        }
        
        return 'Invalid value format';
    }
    
    // Hide create new section
    function hideCreateNewSection() {
        createNewSection.style.display = 'none';
    }
    
    // Create new subject type
    async function createNewSubjectType() {
        const displayNameInput = container.querySelector('.new-display-name');
        const valueInput = container.querySelector('.new-value');
        
        const displayName = displayNameInput.value.trim();
        const value = valueInput.value.trim();
        
        if (!displayName || !value) {
            alert('Please fill in both Display Name and Value fields.');
            return;
        }
        
        try {
            // Create new subject type via AJAX
            const response = await fetch('/integrations/api/create-subject-type/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                },
                body: JSON.stringify({
                    display_name: displayName,
                    value: value
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                const newChoice = [data.id, data.display_name, data.value];
                
                // Add to choices list
                allChoices.push(newChoice);
                allChoices.sort((a, b) => a[1].localeCompare(b[1]));
                
                // Select the new choice
                selectChoice(newChoice);
                
                // Hide create new section
                hideCreateNewSection();
                
                console.log('Created new subject type:', newChoice);
            } else {
                const error = await response.json();
                alert('Error creating subject type: ' + (error.message || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error creating subject type:', error);
            alert('Error creating subject type. Please try again.');
        }
    }
    
    // Initialize
    init();
}

// CSS styles (injected dynamically) - only inject once
(function() {
    if (!document.getElementById('subject-type-autocomplete-styles')) {
        const styles = `
            .subject-type-autocomplete-container .autocomplete-dropdown {
                width: 100%;
                max-height: 200px;
                overflow-y: auto;
                border: 1px solid #ced4da;
                border-radius: 0.375rem;
                box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15);
            }
            
            .subject-type-autocomplete-container .choice-item {
                cursor: pointer;
                padding: 0.5rem 0.75rem;
            }
            
            .subject-type-autocomplete-container .choice-item:hover {
                background-color: #f8f9fa;
            }
            
            .subject-type-autocomplete-container .show-create-new {
                cursor: pointer;
                padding: 0.5rem 0.75rem;
                border-top: 1px solid #dee2e6;
            }
            
            .subject-type-autocomplete-container .show-create-new:hover {
                background-color: #e3f2fd;
            }
            
            .subject-type-autocomplete-container .dropdown-toggle::after {
                display: none;
            }
            
            .subject-type-autocomplete-container .input-group .form-control {
                border-top-right-radius: 0;
                border-bottom-right-radius: 0;
            }
            
            .subject-type-autocomplete-container .input-group .btn {
                border-top-left-radius: 0;
                border-bottom-left-radius: 0;
            }
        `;
        
        const styleSheet = document.createElement('style');
        styleSheet.id = 'subject-type-autocomplete-styles';
        styleSheet.textContent = styles;
        document.head.appendChild(styleSheet);
    }
})();
