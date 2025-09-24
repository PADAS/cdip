/**
 * Device Searchable Multi-Select Widget
 * Provides a searchable multiselect interface specifically for devices
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all device searchable multiselect widgets
    const deviceWidgets = document.querySelectorAll('[data-toggle="searchable-multiselect"]');
    deviceWidgets.forEach(initDeviceWidget);
});

function initDeviceWidget(container) {
    const widgetId = container.id;
    const searchInput = container.querySelector('.search-input');
    const availableList = container.querySelector('.available-list');
    const selectedList = container.querySelector('.selected-list');
    const hiddenInputsContainer = container.querySelector('.hidden-inputs');
    
    // Get options from data attributes or use defaults
    const options = {
        choices: JSON.parse(container.dataset.choices || '[]'),
        selected: JSON.parse(container.dataset.selected || '[]')
    };
    
    console.log('Initializing device widget with options:', options);
    
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
            selectedList.innerHTML = `<div class="text-muted">No devices selected</div>`;
        } else {
            selectedValues.forEach(value => {
                const choice = allChoices.find(c => c[0] == value);
                if (choice) {
                    // For devices: choice[0]=id, choice[1]=name, choice[2]=external_id, choice[3]=owner, choice[4]=type, choice[5]=config
                    const item = createSelectedItem(choice[0], choice[1], choice[2], choice[3], choice[4], choice[5]);
                    selectedList.appendChild(item);
                }
            });
        }
        
        // Always update hidden inputs, even when no items are selected
        updateHiddenInputs();
    }
    
    // Render available items (devices only)
    function renderAvailableItems() {
        availableList.innerHTML = '';
        
        const availableChoices = filteredChoices.filter(choice => !selectedValues.has(choice[0]));
        
        if (availableChoices.length === 0) {
            availableList.innerHTML = `<div class="text-muted">No devices available</div>`;
            return;
        }
        
        availableChoices.forEach(choice => {
            // For devices: choice[0]=id, choice[1]=name, choice[2]=external_id, choice[3]=owner, choice[4]=type, choice[5]=config
            const item = createAvailableItem(choice[0], choice[1], choice[2], choice[3], choice[4], choice[5]);
            availableList.appendChild(item);
        });
    }
    
    // Create a selected item element as a list item (devices only)
    function createSelectedItem(value, name, externalId, owner, type, config) {
        const item = document.createElement('div');
        item.className = 'list-group-item list-group-item-action list-group-item-success d-flex justify-content-between align-items-center mb-1';
        
        const infoHtml = `
            <div class="d-flex justify-content-between align-items-center w-100">
                <div class="flex-grow-1">
                    <div class="row">
                        <div class="col-3">
                            <strong>${name || 'N/A'}</strong>
                        </div>
                        <div class="col-3">
                            <span class="text-muted">${externalId}</span>
                        </div>
                        <div class="col-3">
                            <span class="text-muted">${type}</span>
                        </div>
                        <div class="col-3">
                            <span class="text-muted">${owner}</span>
                        </div>
                    </div>
                </div>
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
    
    // Create an available item element (devices only)
    function createAvailableItem(value, name, externalId, owner, type, config) {
        const item = document.createElement('div');
        item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center mb-1';
        item.style.cursor = 'pointer';
        
        const infoHtml = `
            <div class="d-flex justify-content-between align-items-center w-100">
                <div class="flex-grow-1">
                    <div class="row">
                        <div class="col-3">
                            <strong>${name || 'N/A'}</strong>
                        </div>
                        <div class="col-3">
                            <span class="text-muted">${externalId}</span>
                        </div>
                        <div class="col-3">
                            <span class="text-muted">${type}</span>
                        </div>
                        <div class="col-3">
                            <span class="text-muted">${owner}</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        item.innerHTML = `
            ${infoHtml}
            <button type="button" class="btn btn-sm btn-outline-success add-item" data-value="${value}">
                <i class="fas fa-plus"></i>
            </button>
        `;
        
        // Add click functionality to add item
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
    
    // Update hidden inputs
    function updateHiddenInputs() {
        // Clear existing hidden inputs
        hiddenInputsContainer.innerHTML = '';
        
        // Add hidden inputs for each selected value
        selectedValues.forEach(value => {
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = container.dataset.name || 'devices';
            hiddenInput.value = value;
            hiddenInputsContainer.appendChild(hiddenInput);
        });
        
        console.log('Updated hidden inputs:', hiddenInputsContainer.innerHTML);
    }
    
    // Setup event listeners
    function setupEventListeners() {
        // Search functionality - filters devices only
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            filteredChoices = allChoices.filter(choice => {
                // For devices: choice[0]=id, choice[1]=name, choice[2]=external_id, choice[3]=owner, choice[4]=type, choice[5]=config
                let matches = choice[1].toLowerCase().includes(searchTerm);  // name
                matches = matches || 
                         choice[2].toLowerCase().includes(searchTerm) ||  // external_id
                         choice[3].toLowerCase().includes(searchTerm) ||  // owner
                         choice[4].toLowerCase().includes(searchTerm) ||  // type
                         choice[5].toLowerCase().includes(searchTerm);    // config
                
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
