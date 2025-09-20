/**
 * Searchable MultiSelect Widget
 * Provides a user-friendly interface for selecting multiple items from a searchable list
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
            selectedList.innerHTML = '<div class="text-muted">No destinations selected</div>';
            return;
        }
        
        selectedValues.forEach(value => {
            const choice = allChoices.find(c => c[0] == value);
            if (choice) {
                const item = createSelectedItem(choice[0], choice[1]);
                selectedList.appendChild(item);
            }
        });
        
        updateHiddenInputs();
    }
    
    // Render available items
    function renderAvailableItems() {
        availableList.innerHTML = '';
        
        const availableChoices = filteredChoices.filter(choice => !selectedValues.has(choice[0]));
        
        if (availableChoices.length === 0) {
            availableList.innerHTML = '<div class="text-muted">No destinations available</div>';
            return;
        }
        
        availableChoices.forEach(choice => {
            const item = createAvailableItem(choice[0], choice[1]);
            availableList.appendChild(item);
        });
    }
    
    // Create a selected item element
    function createSelectedItem(value, label) {
        const item = document.createElement('div');
        item.className = 'selected-item d-flex justify-content-between align-items-center p-2 mb-1 bg-primary text-white rounded';
        item.innerHTML = `
            <span>${label}</span>
            <button type="button" class="btn btn-sm btn-outline-light remove-item" data-value="${value}">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Add remove functionality
        item.querySelector('.remove-item').addEventListener('click', () => {
            selectedValues.delete(value);
            renderSelectedItems();
            renderAvailableItems();
        });
        
        return item;
    }
    
    // Create an available item element
    function createAvailableItem(value, label) {
        const item = document.createElement('div');
        item.className = 'available-item p-2 mb-1 border rounded cursor-pointer';
        item.style.cursor = 'pointer';
        item.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <span>${label}</span>
                <button type="button" class="btn btn-sm btn-outline-primary add-item" data-value="${value}">
                    <i class="fas fa-plus"></i>
                </button>
            </div>
        `;
        
        // Add click functionality to the entire item
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.add-item')) {
                addItem(value);
            }
        });
        
        // Add button click functionality
        item.querySelector('.add-item').addEventListener('click', () => {
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
        selectedArray.forEach((value, index) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = `${options.name}_${index}`;
            input.value = value;
            hiddenInputsContainer.appendChild(input);
        });
        
        // Debug: log the hidden inputs being created
        console.log('Hidden inputs created:');
        selectedArray.forEach((value, index) => {
            console.log(`  ${options.name}_${index} = ${value}`);
        });
    }
    
    // Setup event listeners
    function setupEventListeners() {
        // Search functionality
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            filteredChoices = allChoices.filter(choice => 
                choice[1].toLowerCase().includes(searchTerm)
            );
            renderAvailableItems();
        });
        
        // Clear search when clicking outside
        document.addEventListener('click', (e) => {
            if (!container.contains(e.target)) {
                searchInput.value = '';
                filteredChoices = [...allChoices];
                renderAvailableItems();
            }
        });
    }
    
    // Initialize the widget
    init();
}

// CSS styles (injected dynamically)
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
    
    .selected-item, .available-item {
        transition: all 0.2s ease-in-out;
    }
    
    .available-item:hover {
        background-color: #f8f9fa;
        border-color: #86b7fe !important;
    }
    
    .selected-list, .available-list {
        max-height: 200px;
        overflow-y: auto;
        border: 1px solid #dee2e6;
        border-radius: 0.375rem;
        padding: 0.5rem;
        background-color: #f8f9fa;
    }
    
    .form-label {
        font-weight: 600;
        margin-bottom: 0.5rem;
        color: #495057;
    }
    
    .cursor-pointer {
        cursor: pointer;
    }
    
    .btn-sm {
        padding: 0.25rem 0.5rem;
        font-size: 0.875rem;
        border-radius: 0.25rem;
    }
`;

// Inject styles
if (!document.getElementById('searchable-multiselect-styles')) {
    const styleSheet = document.createElement('style');
    styleSheet.id = 'searchable-multiselect-styles';
    styleSheet.textContent = styles;
    document.head.appendChild(styleSheet);
}
