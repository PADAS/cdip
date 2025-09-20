/**
 * Searchable MultiSelect Widget
 * Provides a user-friendly interface for selecting multiple items from a searchable list
 * Updated: Fixed empty selection bug - v1.1
 */

function initSearchableMultiSelect(widgetId, options) {
    const container = document.getElementById(widgetId + '_container');
    const searchInput = document.getElementById(widgetId + '_search');
    const selectedList = document.getElementById(widgetId + '_selected');
    const availableList = document.getElementById(widgetId + '_available');
    const hiddenInputsContainer = container.querySelector('.hidden-inputs');
    
    let allChoices = options.choices || [];
    let selectedValues = new Set(options.selected || []);
    let filteredChoices = [...allChoices];
    
    // Initialize the widget
    function init() {
        renderSelectedItems();
        renderAvailableItems();
        setupEventListeners();
    }
    
    // Render selected items
    function renderSelectedItems() {
        selectedList.innerHTML = '';
        
        if (selectedValues.size === 0) {
            selectedList.innerHTML = `<div class="text-muted">No destinations selected</div>`;
        } else {
            selectedValues.forEach(value => {
                const choice = allChoices.find(c => c[0] == value);
                if (choice) {
                    // For destinations: choice[0]=id, choice[1]=name, choice[2]=owner, choice[3]=type, choice[4]=endpoint
                    const item = createSelectedItem(choice[0], choice[1], choice[2], choice[3], choice[4], undefined);
                    selectedList.appendChild(item);
                }
            });
        }
        
        // Always update hidden inputs, even when no items are selected
        updateHiddenInputs();
    }
    
    // Render available items (destinations only)
    function renderAvailableItems() {
        availableList.innerHTML = '';
        
        const availableChoices = filteredChoices.filter(choice => !selectedValues.has(choice[0]));
        
        if (availableChoices.length === 0) {
            availableList.innerHTML = `<div class="text-muted">No destinations available</div>`;
            return;
        }
        
        availableChoices.forEach(choice => {
            // For destinations: choice[0]=id, choice[1]=name, choice[2]=owner, choice[3]=type, choice[4]=endpoint
            const item = createAvailableItem(choice[0], choice[1], choice[2], choice[3], choice[4], undefined);
            availableList.appendChild(item);
        });
    }
    
    // Create a selected item element as a list item (destinations only)
    function createSelectedItem(value, label, owner, type, endpoint, externalId) {
        const item = document.createElement('div');
        item.className = 'list-group-item list-group-item-action list-group-item-success d-flex justify-content-between align-items-center mb-1';
        
        const infoHtml = `
            <div>
                <h6 class="mb-1">${label}</h6>
                <small class="text-muted">${owner} • ${type}</small>
                <br>
                <small class="text-muted">${endpoint}</small>
            </div>
        `;
        
        item.innerHTML = `
            ${infoHtml}
            <button type="button" class="btn btn-sm btn-outline-danger remove-item" data-value="${value}">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Add remove functionality
        item.querySelector('.remove-item').addEventListener('click', (e) => {
            e.stopPropagation();
            selectedValues.delete(value);
            renderSelectedItems();
            renderAvailableItems();
        });
        
        return item;
    }
    
    // Create an available item element (destinations only)
    function createAvailableItem(value, label, owner, type, endpoint, externalId) {
        const item = document.createElement('div');
        item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center mb-1';
        item.style.cursor = 'pointer';
        
        // This function is only used for destinations now
        const infoHtml = `
            <div>
                <h6 class="mb-1">${label}</h6>
                <small class="text-muted">${owner} • ${type}</small>
                <br>
                <small class="text-muted">${endpoint}</small>
            </div>
        `;
        
        item.innerHTML = `
            ${infoHtml}
            <button type="button" class="btn btn-sm btn-outline-primary add-item" data-value="${value}">
                <i class="fas fa-plus"></i>
            </button>
        `;
        
        // Add click functionality to the entire item
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.add-item')) {
                addItem(value);
            }
        });
        
        // Add button click functionality
        item.querySelector('.add-item').addEventListener('click', (e) => {
            e.stopPropagation();
            addItem(value);
        });
        
        return item;
    }
    
    // Add an item to selected
    function addItem(value) {
        selectedValues.add(value);
        renderSelectedItems();
        renderAvailableItems();
    }
    
    // Update hidden inputs for form submission
    function updateHiddenInputs() {
        hiddenInputsContainer.innerHTML = '';
        
        // Convert Set to Array and use sequential indices
        const selectedArray = Array.from(selectedValues);
        
        if (selectedArray.length === 0) {
            // When no items are selected, create a single hidden input with empty value
            // This ensures Django knows the field should be cleared
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = `${options.name}_0`;
            input.value = '';
            hiddenInputsContainer.appendChild(input);
            console.log('Empty selection: created single hidden input with empty value');
        } else {
            // Create inputs for each selected item
            selectedArray.forEach((value, index) => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = `${options.name}_${index}`;
                input.value = value;
                hiddenInputsContainer.appendChild(input);
            });
        }
        
        // Debug: log the hidden inputs being created
        console.log('Hidden inputs created:');
        const allInputs = hiddenInputsContainer.querySelectorAll('input');
        allInputs.forEach((input, index) => {
            console.log(`  ${input.name} = ${input.value}`);
        });
    }
    
    // Setup event listeners
    function setupEventListeners() {
        // Search functionality - filters destinations only
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            filteredChoices = allChoices.filter(choice => {
                // For destinations: choice[0]=id, choice[1]=name, choice[2]=owner, choice[3]=type, choice[4]=endpoint
                let matches = choice[1].toLowerCase().includes(searchTerm);  // name
                matches = matches || 
                         choice[2].toLowerCase().includes(searchTerm) ||  // owner
                         choice[3].toLowerCase().includes(searchTerm) ||  // type
                         choice[4].toLowerCase().includes(searchTerm);    // endpoint
                
                return matches;
            });
            renderSelectedItems();
            renderAvailableItems();
        });
        
        // Clear search when clicking outside
        document.addEventListener('click', (e) => {
            if (!container.contains(e.target)) {
                searchInput.value = '';
                filteredChoices = [...allChoices];
                renderSelectedItems();
                renderAvailableItems();
            }
        });
    }
    
    // Initialize the widget
    init();
}

// CSS styles (injected dynamically) - only inject once
(function() {
    if (!document.getElementById('searchable-multiselect-styles')) {
        const styles = `
            .searchable-multiselect-container {
                border: 1px solid #dee2e6;
                border-radius: 0.375rem;
                padding: 1rem;
                background-color: #fff;
            }
            
            .search-input-container .search-input {
                border-radius: 0.375rem;
                border: 1px solid #ced4da;
                padding: 0.5rem 0.75rem;
            }
            
            .search-input-container .search-input:focus {
                border-color: #86b7fe;
                outline: 0;
                box-shadow: 0 0 0 0.25rem rgba(13, 110, 253, 0.25);
            }
            
            .destination-card {
                transition: all 0.2s ease-in-out;
            }
            
            .available-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            
            .selected-list, .available-list {
                max-height: 400px;
                overflow-y: auto;
                border: 1px solid #dee2e6;
                border-radius: 0.375rem;
                padding: 0;
                background-color: #f8f9fa;
            }
            
            .selected-list .list-group-item, .available-list .list-group-item {
                border: none;
                border-bottom: 1px solid #dee2e6;
                border-radius: 0;
            }
            
            .selected-list .list-group-item:last-child, .available-list .list-group-item:last-child {
                border-bottom: none;
            }
            
            .info-label {
                color: #6c757d;
                font-size: 0.875rem;
                margin-right: 0.5rem;
            }
            
            .info-value {
                color: #495057;
                font-size: 0.875rem;
            }
            
            .info-row {
                display: flex;
                align-items: flex-start;
            }
            
            .cursor-pointer {
                cursor: pointer;
            }
            
            .btn-sm {
                padding: 0.25rem 0.5rem;
                font-size: 0.875rem;
                border-radius: 0.25rem;
            }
            
            .text-break {
                word-break: break-all;
            }
            
            .card {
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .card:hover {
                box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            }
        `;
        
        const styleSheet = document.createElement('style');
        styleSheet.id = 'searchable-multiselect-styles';
        styleSheet.textContent = styles;
        document.head.appendChild(styleSheet);
    }
})();
