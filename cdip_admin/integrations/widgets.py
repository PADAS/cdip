from django import forms
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse


class SearchableMultiSelectWidget(forms.Widget):
    """
    A custom widget that provides a searchable multiselect interface
    for ManyToManyField relationships.
    """
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'searchable-multiselect',
            'data-toggle': 'searchable-multiselect'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = []
        
        # Convert value to list of strings if it's a QuerySet or list of objects
        if hasattr(value, '__iter__') and not isinstance(value, str):
            try:
                # If it's a QuerySet or list of model instances, extract the primary keys
                if hasattr(value, 'values_list'):
                    # It's a QuerySet
                    value = list(value.values_list('pk', flat=True))
                elif value and hasattr(value[0], 'pk'):
                    # It's a list of model instances
                    value = [str(obj.pk) for obj in value]
                else:
                    # It's already a list of values
                    value = [str(v) for v in value]
            except (AttributeError, IndexError):
                # Fallback to string conversion
                value = [str(v) for v in value] if value else []
        elif value:
            value = [str(value)]
        else:
            value = []
        
        # Ensure attrs is a dictionary
        if attrs is None:
            attrs = {}
        
        # Get the field instance to access choices
        field = self.attrs.get('field')
        if not field:
            return format_html('<div class="alert alert-warning">Field not available</div>')
        
        # Get all available choices
        choices = []
        # First try to get choices from attrs (set by widget_attrs)
        if 'choices' in attrs:
            choices = attrs['choices']
        elif hasattr(field, 'queryset') and field.queryset:
            try:
                queryset = field.queryset.all().select_related('owner', 'type')
                for obj in queryset:
                    # Create choice tuple with: (id, name, owner, type, endpoint)
                    choices.append((
                        str(obj.pk), 
                        obj.name or str(obj),
                        obj.owner.name if obj.owner else 'N/A',
                        obj.type.name if obj.type else 'N/A',
                        obj.endpoint or 'N/A'
                    ))
            except Exception as e:
                pass  # Silently handle queryset errors
        elif hasattr(field, 'choices') and field.choices:
            choices = field.choices
        
        # Convert value to list of strings for comparison
        if isinstance(value, (list, tuple)):
            selected_values = [str(v) for v in value]
        else:
            selected_values = [str(value)] if value else []
        
        # Render the widget HTML
        widget_id = attrs.get('id', f'id_{name}')
        
        html = format_html(
                   '''
                   <div class="searchable-multiselect-container" id="{widget_id}_container">
                       <div class="search-input-container mb-3">
                           <input type="text" 
                                  class="form-control search-input" 
                                  placeholder="Search by name, owner, type, or endpoint..." 
                                  id="{widget_id}_search">
                       </div>
                       
                       <div class="row">
                           <div class="col-md-6">
                               <div class="available-items">
                                   <h6 class="text-muted mb-3">Available Destinations</h6>
                                   <div class="available-list" id="{widget_id}_available">
                                       <!-- Available items will be populated here -->
                                   </div>
                               </div>
                           </div>
                           
                           <div class="col-md-6">
                               <div class="selected-items">
                                   <h6 class="text-muted mb-3">Selected Destinations</h6>
                                   <div class="selected-list" id="{widget_id}_selected">
                                       <!-- Selected items will be populated here -->
                                   </div>
                               </div>
                           </div>
                       </div>
                       
                       <!-- Hidden inputs for selected values -->
                       <div class="hidden-inputs">
                           <!-- Will be populated by JavaScript -->
                       </div>
                   </div>
                   ''',
                   widget_id=widget_id
               )
        
        # Add JavaScript to initialize the widget
        import json
        from django.utils.safestring import mark_safe
        
        choices_json = mark_safe(json.dumps(choices))
        selected_json = mark_safe(json.dumps(selected_values))
        
        # Read the JavaScript file content and include it inline
        import os
        js_file_path = os.path.join(os.path.dirname(__file__), 'static', 'integrations', 'js', 'searchable-multiselect.js')
        
        js_content = ""
        if os.path.exists(js_file_path):
            with open(js_file_path, 'r') as f:
                js_content = f.read()
        
        js = format_html(
            '''
            <script>
            {js_content}
            
            document.addEventListener('DOMContentLoaded', function() {{
                console.log('DOM loaded, initializing searchable multiselect...');
                console.log('Widget ID:', '{widget_id}');
                console.log('Choices:', {choices_json});
                console.log('Selected:', {selected_json});
                
                try {{
                    initSearchableMultiSelect('{widget_id}', {{
                        choices: {choices_json},
                        selected: {selected_json},
                        name: '{name}'
                    }});
                    console.log('Searchable multiselect initialized successfully');
                }} catch (error) {{
                    console.error('Error initializing searchable multiselect:', error);
                }}
                
                // Add debugging for form submission
                const form = document.querySelector('form');
                console.log('Form found:', form);
                if (form) {{
                    form.addEventListener('submit', function(e) {{
                        console.log('=== FORM SUBMISSION START ===');
                        console.log('Form submitted');
                        const hiddenInputs = document.querySelectorAll('input[name^="{name}_"]');
                        console.log('Hidden inputs found:', hiddenInputs.length);
                        hiddenInputs.forEach((input, index) => {{
                            console.log(`Hidden input ${{index}}: name=${{input.name}}, value=${{input.value}}`);
                        }});
                        
                        // Also log all form data
                        const formData = new FormData(form);
                        console.log('All form data:');
                        for (let [key, value] of formData.entries()) {{
                            console.log(`  ${{key}}: ${{value}}`);
                        }}
                        console.log('=== FORM SUBMISSION END ===');
                    }});
                }} else {{
                    console.error('No form found on page');
                }}
            }});
            </script>
            ''',
            js_content=mark_safe(js_content),
            widget_id=widget_id,
            choices_json=choices_json,
            selected_json=selected_json,
            name=name
        )
        
        return mark_safe(html + js)
    
    def value_from_datadict(self, data, files, name):
        """Extract selected values from form data."""
        values = []
        
        # Look for values with the pattern name_0, name_1, etc.
        i = 0
        while True:
            key = f"{name}_{i}"
            if key in data:
                value = data[key]
                # Skip empty values (they indicate clearing the selection)
                if value and value.strip():
                    values.append(value)
                i += 1
            else:
                break
        
        # Also check for a single value with the name
        if name in data:
            values.append(data[name])
        
        # Handle the case where field names might include UUIDs
        # Look for any keys that start with the field name
        for key in data.keys():
            if key.startswith(f"{name}_") and key not in [f"{name}_{i}" for i in range(len(values))]:
                # This might be a UUID-based field name
                value = data[key]
                # Only add non-empty values
                if value and value.strip():
                    values.append(value)
        
        return values


class SearchableMultiSelectField(forms.ModelMultipleChoiceField):
    """
    A custom field that uses the SearchableMultiSelectWidget.
    """
    
    def __init__(self, *args, **kwargs):
        # Create the widget instance first
        widget = SearchableMultiSelectWidget()
        kwargs['widget'] = widget
        super().__init__(*args, **kwargs)
        # Store the field reference in the widget after initialization
        self.widget.attrs['field'] = self
    
    def bound_data(self, data, initial):
        """Override to ensure initial values are properly handled."""
        if initial is None:
            initial = []
        return super().bound_data(data, initial)
        
    def widget_attrs(self, widget):
        """Override to pass choices to the widget."""
        attrs = super().widget_attrs(widget)
        # Don't set choices here - let the widget get them during render
        return attrs


class DeviceSearchableMultiSelectWidget(forms.Widget):
    """
    A custom widget that provides a searchable multiselect interface
    for Device ManyToManyField relationships.
    """
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'searchable-multiselect',
            'data-toggle': 'searchable-multiselect'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = []
        
        # Convert value to list of strings if it's a QuerySet or list of objects
        if hasattr(value, '__iter__') and not isinstance(value, str):
            try:
                # If it's a QuerySet or list of model instances, extract the primary keys
                if hasattr(value, 'values_list'):
                    # It's a QuerySet
                    value = list(value.values_list('pk', flat=True))
                elif value and hasattr(value[0], 'pk'):
                    # It's a list of model instances
                    value = [str(obj.pk) for obj in value]
                else:
                    # It's already a list of values
                    value = [str(v) for v in value]
            except (AttributeError, IndexError):
                # Fallback to string conversion
                value = [str(v) for v in value] if value else []
        elif value:
            value = [str(value)]
        else:
            value = []
        
        # Ensure attrs is a dictionary
        if attrs is None:
            attrs = {}
        
        # Get the field instance to access choices
        field = self.attrs.get('field')
        if not field:
            return format_html('<div class="alert alert-warning">Field not available</div>')
        
        # Get all available choices
        choices = []
        # First try to get choices from attrs (set by widget_attrs)
        if 'choices' in attrs:
            choices = attrs['choices']
        elif hasattr(field, 'queryset') and field.queryset:
            try:
                queryset = field.queryset.all().select_related('inbound_configuration__owner', 'inbound_configuration__type')
                for obj in queryset:
                    # Create choice tuple with: (id, name, external_id, owner, type, inbound_config)
                    choices.append((
                        str(obj.pk), 
                        obj.name or str(obj),
                        obj.external_id or 'N/A',
                        obj.owner.name if obj.owner else 'N/A',
                        obj.inbound_configuration.type.name if obj.inbound_configuration and obj.inbound_configuration.type else 'N/A',
                        obj.inbound_configuration.name if obj.inbound_configuration else 'N/A'
                    ))
            except Exception as e:
                pass  # Silently handle queryset errors
        elif hasattr(field, 'choices') and field.choices:
            choices = field.choices
        
        # Convert value to list of strings for comparison
        if isinstance(value, (list, tuple)):
            selected_values = [str(v) for v in value]
        else:
            selected_values = [str(value)] if value else []
        
        # Render the widget HTML
        widget_id = attrs.get('id', f'id_{name}')
        
        # Import json for data serialization
        import json
        
        html = format_html(
                   '''
                   <div class="searchable-multiselect-container" id="{widget_id}_container" 
                        data-choices='{choices_json}' 
                        data-selected='{selected_json}' 
                        data-name="{name}">
                       <div class="search-input-container mb-3">
                           <input type="text" 
                                  class="form-control search-input" 
                                  placeholder="Search devices by name, external ID, owner, type, or configuration..." 
                                  id="{widget_id}_search">
                       </div>
                       
                       <div class="row">
                           <div class="col-md-6">
                               <div class="available-items">
                                   <h6 class="text-muted mb-3">Available Devices</h6>
                                   <div class="device-headers mb-2">
                                       <div class="row text-muted small fw-bold">
                                           <div class="col-3">Name</div>
                                           <div class="col-3">External ID</div>
                                           <div class="col-3">Type</div>
                                           <div class="col-3">Owner</div>
                                       </div>
                                   </div>
                                   <div class="available-list" id="{widget_id}_available">
                                       <!-- Available items will be populated here -->
                                   </div>
                               </div>
                           </div>
                           
                           <div class="col-md-6">
                               <div class="selected-items">
                                   <h6 class="text-muted mb-3">Selected Devices</h6>
                                   <div class="device-headers mb-2">
                                       <div class="row text-muted small fw-bold">
                                           <div class="col-3">Name</div>
                                           <div class="col-3">External ID</div>
                                           <div class="col-3">Type</div>
                                           <div class="col-3">Owner</div>
                                       </div>
                                   </div>
                                   <div class="selected-list" id="{widget_id}_selected">
                                       <!-- Selected items will be populated here -->
                                   </div>
                               </div>
                           </div>
                       </div>
                       
                       <!-- Hidden inputs for selected values -->
                       <div class="hidden-inputs">
                           <!-- Will be populated by JavaScript -->
                       </div>
                   </div>
                   ''',
                   widget_id=widget_id,
                   choices_json=json.dumps(choices),
                   selected_json=json.dumps(selected_values),
                   name=name
               )
        
        # Add JavaScript to initialize the widget
        import json
        from django.utils.safestring import mark_safe
        
        choices_json = mark_safe(json.dumps(choices))
        selected_json = mark_safe(json.dumps(selected_values))
        
        # Read the JavaScript file content and include it inline
        import os
        js_file_path = os.path.join(os.path.dirname(__file__), 'static', 'integrations', 'js', 'device-searchable-multiselect.js')
        
        js_content = ""
        if os.path.exists(js_file_path):
            with open(js_file_path, 'r') as f:
                js_content = f.read()
        
        js = format_html(
            '''
            <script>
            {js_content}
            
            document.addEventListener('DOMContentLoaded', function() {{
                console.log('DOM loaded, initializing device searchable multiselect...');
                console.log('Widget ID:', '{widget_id}');
                console.log('Choices:', {choices_json});
                console.log('Selected:', {selected_json});
                
                try {{
                    initDeviceWidget(document.getElementById('{widget_id}_container'));
                    console.log('Device searchable multiselect initialized successfully');
                }} catch (error) {{
                    console.error('Error initializing device searchable multiselect:', error);
                }}
                
                // Add debugging for form submission
                const form = document.querySelector('form');
                console.log('Form found:', form);
                if (form) {{
                    form.addEventListener('submit', function(e) {{
                        console.log('=== FORM SUBMISSION START ===');
                        console.log('Form submitted');
                        const hiddenInputs = document.querySelectorAll('input[name^="{name}_"]');
                        console.log('Hidden inputs found:', hiddenInputs.length);
                        hiddenInputs.forEach((input, index) => {{
                            console.log(`Hidden input ${{index}}: name=${{input.name}}, value=${{input.value}}`);
                        }});
                        
                        // Also log all form data
                        const formData = new FormData(form);
                        console.log('All form data:');
                        for (let [key, value] of formData.entries()) {{
                            console.log(`  ${{key}}: ${{value}}`);
                        }}
                        console.log('=== FORM SUBMISSION END ===');
                    }});
                }} else {{
                    console.error('No form found on page');
                }}
            }});
            </script>
            ''',
            js_content=mark_safe(js_content),
            widget_id=widget_id,
            choices_json=choices_json,
            selected_json=selected_json,
            name=name
        )
        
        return mark_safe(html + js)
    
    def value_from_datadict(self, data, files, name):
        """Extract selected values from form data."""
        values = []
        
        # Look for values with the pattern name_0, name_1, etc.
        i = 0
        while True:
            key = f"{name}_{i}"
            if key in data:
                value = data[key]
                # Skip empty values (they indicate clearing the selection)
                if value and value.strip():
                    values.append(value)
                i += 1
            else:
                break
        
        # Also check for a single value with the name
        if name in data:
            values.append(data[name])
        
        # Handle the case where field names might include UUIDs
        # Look for any keys that start with the field name
        for key in data.keys():
            if key.startswith(f"{name}_") and key not in [f"{name}_{i}" for i in range(len(values))]:
                # This might be a UUID-based field name
                value = data[key]
                # Only add non-empty values
                if value and value.strip():
                    values.append(value)
        
        return values


class DeviceSearchableMultiSelectField(forms.ModelMultipleChoiceField):
    """
    A custom field that uses the DeviceSearchableMultiSelectWidget.
    """
    
    def __init__(self, *args, **kwargs):
        # Create the widget instance first
        widget = DeviceSearchableMultiSelectWidget()
        kwargs['widget'] = widget
        super().__init__(*args, **kwargs)
        # Store the field reference in the widget after initialization
        self.widget.attrs['field'] = self
    
    def bound_data(self, data, initial):
        """Override to ensure initial values are properly handled."""
        if initial is None:
            initial = []
        return super().bound_data(data, initial)
        
    def widget_attrs(self, widget):
        """Override to pass choices to the widget."""
        attrs = super().widget_attrs(widget)
        # Don't set choices here - let the widget get them during render
        return attrs


class SubjectTypeAutocompleteWidget(forms.Widget):
    """
    A widget for selecting subject types with auto-complete and the ability to create new ones.
    """
    template_name = 'integrations/widgets/subject_type_autocomplete.html'

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'subject-type-autocomplete',
            'data-toggle': 'subject-type-autocomplete',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = ''

        # Get all available subject types
        from integrations.models import SubjectType
        subject_types = SubjectType.objects.all().order_by('display_name')
        choices = [(str(st.id), st.display_name, st.value) for st in subject_types]

        if attrs is None:
            attrs = {}

        widget_id = attrs.get('id', f'id_{name}')

        html = format_html(
            '''
            <div class="subject-type-autocomplete-container" id="{widget_id}_container">
                <div class="input-group">
                    <input type="text" 
                           class="form-control autocomplete-input" 
                           placeholder="Type to search or create new subject type..." 
                           id="{widget_id}_input"
                           autocomplete="off">
                    <input type="hidden" 
                           name="{name}" 
                           id="{widget_id}_hidden"
                           value="{value}">
                    <button type="button" 
                            class="btn btn-outline-secondary dropdown-toggle" 
                            id="{widget_id}_dropdown"
                            data-toggle="dropdown">
                        <i class="fas fa-chevron-down"></i>
                    </button>
                    <div class="dropdown-menu autocomplete-dropdown" 
                         id="{widget_id}_dropdown_menu">
                        <!-- Options will be populated by JavaScript -->
                    </div>
                </div>
                
                <div class="selected-subject-type mt-2" id="{widget_id}_selected" style="display: none;">
                    <div class="alert alert-info d-flex justify-content-between align-items-center">
                        <span>
                            <strong>Selected:</strong> <span class="selected-name"></span>
                            <small class="text-muted">(<span class="selected-value"></span>)</small>
                        </span>
                        <button type="button" class="btn btn-sm btn-outline-danger clear-selection">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
                
                <div class="create-new-section mt-2" id="{widget_id}_create_new" style="display: none;">
                    <div class="alert alert-warning">
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <strong>Create New Subject Type</strong>
                            <button type="button" class="btn btn-sm btn-outline-secondary cancel-create">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <label class="form-label">Display Name:</label>
                                <input type="text" 
                                       class="form-control new-display-name" 
                                       placeholder="e.g., Elephant">
                            </div>
                            <div class="col-md-6">
                                <label class="form-label">Value (Slug):</label>
                                <input type="text" 
                                       class="form-control new-value" 
                                       placeholder="e.g., elephant"
                                       maxlength="32">
                                <div class="validation-message invalid-feedback" style="display: none;"></div>
                                <small class="form-text text-muted">Up to 32 characters, lowercase letters, digits, underscores, and hyphens only</small>
                            </div>
                        </div>
                        <button type="button" class="btn btn-primary btn-sm mt-2 create-subject-type" disabled>
                            <i class="fas fa-plus"></i> Create & Select
                        </button>
                    </div>
                </div>
            </div>
            ''',
            widget_id=widget_id,
            name=name,
            value=value
        )

        # Add JavaScript to initialize the widget
        import json
        import os
        from django.utils.safestring import mark_safe
        from django.conf import settings
        
        # Ensure proper JSON escaping
        choices_json = json.dumps(choices)
        current_value = value if value else ''

        # Read the JavaScript file content and include it inline
        js_file_path = os.path.join(
            settings.BASE_DIR,
            'cdip_admin', 'integrations', 'static', 'integrations', 'js', 'subject-type-autocomplete.js'
        )
        
        js_content = ""
        if os.path.exists(js_file_path):
            with open(js_file_path, 'r') as f:
                js_content = f.read()
        else:
            # Fallback: embed a minimal version of the JavaScript
            js_content = """
            function initSubjectTypeAutocomplete(widgetId, options) {
                console.log('Subject Type Widget: Fallback initialization');
                console.log('Subject Type Widget: allChoices =', options.choices);
                
                const container = document.getElementById(widgetId + '_container');
                const input = document.getElementById(widgetId + '_input');
                const hiddenInput = document.getElementById(widgetId + '_hidden');
                const dropdown = document.getElementById(widgetId + '_dropdown');
                const dropdownMenu = document.getElementById(widgetId + '_dropdown_menu');
                
                if (!container || !input || !hiddenInput || !dropdown || !dropdownMenu) {
                    console.error('Subject Type Widget: Required elements not found');
                    return;
                }
                
                let allChoices = options.choices || [];
                let currentValue = options.currentValue || '';
                
                // Show all choices when dropdown is clicked
                dropdown.addEventListener('click', function() {
                    console.log('Subject Type Widget: Dropdown clicked');
                    dropdownMenu.innerHTML = '';
                    
                    if (allChoices.length === 0) {
                        dropdownMenu.innerHTML = '<div class="dropdown-item-text text-muted">No subject types found</div>';
                        return;
                    }
                    
                    allChoices.forEach(choice => {
                        const item = document.createElement('div');
                        item.className = 'dropdown-item choice-item';
                        item.innerHTML = '<div><strong>' + choice[1] + '</strong><small class="text-muted d-block">' + choice[2] + '</small></div>';
                        item.addEventListener('click', function() {
                            hiddenInput.value = choice[0];
                            input.value = choice[1];
                            dropdownMenu.style.display = 'none';
                            console.log('Subject Type Widget: Selected', choice[1]);
                        });
                        dropdownMenu.appendChild(item);
                    });
                    
                    dropdownMenu.style.display = 'block';
                });
                
                // Hide dropdown when clicking outside
                document.addEventListener('click', function(e) {
                    if (!container.contains(e.target)) {
                        dropdownMenu.style.display = 'none';
                    }
                });
            }
            """

        js = format_html(
            '''
            <script data-widget-id="{widget_id}">
            {js_content}
            
            function initWidget_{widget_id}() {{
                console.log('Initializing subject type autocomplete widget...');
                console.log('Widget ID:', '{widget_id}');
                console.log('Choices:', {choices_json});
                console.log('Current value:', '{current_value}');
                
                if (typeof initSubjectTypeAutocomplete === 'function') {{
                    initSubjectTypeAutocomplete('{widget_id}', {{
                        choices: {choices_json},
                        currentValue: '{current_value}',
                        name: '{name}'
                    }});
                }} else {{
                    console.error('initSubjectTypeAutocomplete function not found');
                }}
            }}
            
            document.addEventListener('DOMContentLoaded', function() {{
                // Store the initialization function globally
                window.initWidget_{widget_id} = initWidget_{widget_id};
                
                // Initialize immediately if the widget is visible
                const container = document.getElementById('{widget_id}_container');
                if (container && container.offsetParent !== null) {{
                    initWidget_{widget_id}();
                }} else {{
                    console.log('Widget {widget_id} not visible yet, will initialize when tab becomes active');
                }}
            }});
            </script>
            ''',
            js_content=mark_safe(js_content),
            widget_id=widget_id,
            choices_json=mark_safe(choices_json),
            current_value=current_value,
            name=name
        )
        
        return mark_safe(html + js)


class SubjectTypeAutocompleteField(forms.ModelChoiceField):
    """
    A custom field that uses the SubjectTypeAutocompleteWidget.
    """
    def __init__(self, *args, **kwargs):
        from integrations.models import SubjectType
        queryset = kwargs.get('queryset', SubjectType.objects.all())
        kwargs['queryset'] = queryset
        widget = SubjectTypeAutocompleteWidget()
        kwargs['widget'] = widget
        super().__init__(*args, **kwargs)


class DeviceGroupSelectWithLinkWidget(forms.Widget):
    """
    A widget that displays a device group select field with a link to manage the selected group.
    """
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control device-group-select-with-link'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def render(self, name, value, attrs=None, renderer=None):
        if attrs is None:
            attrs = {}
        
        # Get the field instance to access choices
        field = self.attrs.get('field')
        if not field:
            return format_html('<div class="alert alert-warning">Field not available</div>')
        
        # Get all available choices
        choices = []
        if hasattr(field, 'queryset') and field.queryset:
            try:
                queryset = field.queryset.all().select_related('owner')
                for obj in queryset:
                    choices.append((str(obj.pk), str(obj)))
            except Exception as e:
                pass  # Silently handle queryset errors
        elif hasattr(field, 'choices') and field.choices:
            choices = field.choices
        
        widget_id = attrs.get('id', f'id_{name}')
        
        # Create the select element
        select_html = f'<select name="{name}" id="{widget_id}" class="form-control">'
        select_html += '<option value="">---------</option>'
        
        for choice_value, choice_label in choices:
            selected = 'selected' if str(choice_value) == str(value) else ''
            select_html += f'<option value="{choice_value}" {selected}>{choice_label}</option>'
        
        select_html += '</select>'
        
        # Create the manage link (only show if a value is selected)
        manage_link_html = ''
        if value:
            manage_link_html = f'''
                <div class="mt-2">
                    <a href="/integrations/devicegroups/{value}/manage" 
                       class="btn btn-sm btn-outline-primary" 
                       target="_blank">
                        <i class="fas fa-cog"></i> Manage Device Group
                    </a>
                </div>
            '''
        
        # Add JavaScript to update the manage link when selection changes
        js_html = f'''
            <script>
            document.addEventListener('DOMContentLoaded', function() {{
                const select = document.getElementById('{widget_id}');
                const manageLinkContainer = document.getElementById('{widget_id}_manage_link');
                
                if (select && manageLinkContainer) {{
                    select.addEventListener('change', function() {{
                        const selectedValue = this.value;
                        if (selectedValue) {{
                            manageLinkContainer.innerHTML = `
                                <div class="mt-2">
                                    <a href="/integrations/devicegroups/${{selectedValue}}/manage" 
                                       class="btn btn-sm btn-outline-primary" 
                                       target="_blank">
                                        <i class="fas fa-cog"></i> Manage Device Group
                                    </a>
                                </div>
                            `;
                        }} else {{
                            manageLinkContainer.innerHTML = '';
                        }}
                    }});
                }}
            }});
            </script>
        '''
        
        html = format_html(
            '''
            <div class="device-group-select-with-link-container">
                {select_html}
                <div id="{widget_id}_manage_link">
                    {manage_link_html}
                </div>
            </div>
            {js_html}
            ''',
            select_html=mark_safe(select_html),
            widget_id=widget_id,
            manage_link_html=mark_safe(manage_link_html),
            js_html=mark_safe(js_html)
        )
        
        return html
    
    def value_from_datadict(self, data, files, name):
        """Extract the selected value from form data."""
        return data.get(name)


class DeviceGroupSelectWithLinkField(forms.ModelChoiceField):
    """
    A custom field that uses the DeviceGroupSelectWithLinkWidget.
    """
    
    def __init__(self, *args, **kwargs):
        from integrations.models import DeviceGroup
        queryset = kwargs.get('queryset', DeviceGroup.objects.all())
        kwargs['queryset'] = queryset
        widget = DeviceGroupSelectWithLinkWidget()
        kwargs['widget'] = widget
        super().__init__(*args, **kwargs)
        # Store the field reference in the widget after initialization
        self.widget.attrs['field'] = self


class DeviceGroupAutoCreateWidget(forms.Widget):
    """
    A widget that displays a message indicating a default device group will be created automatically.
    """
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control device-group-auto-create'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def render(self, name, value, attrs=None, renderer=None):
        widget_id = attrs.get('id', f'id_{name}') if attrs else f'id_{name}'
        
        html = format_html(
            '''
            <div class="device-group-auto-create-container">
                <div class="alert alert-info">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-info-circle me-2"></i>
                        <div>
                            <strong>Default Device Group</strong><br>
                            <small>A default device group will be created automatically when you save this integration configuration.</small>
                        </div>
                    </div>
                </div>
                <input type="hidden" name="{name}" id="{widget_id}" value="">
            </div>
            ''',
            name=name,
            widget_id=widget_id
        )
        
        return html
    
    def value_from_datadict(self, data, files, name):
        """Return empty value since this field is auto-created."""
        return None


class DeviceGroupAutoCreateField(forms.ModelChoiceField):
    """
    A custom field that uses the DeviceGroupAutoCreateWidget.
    """
    
    def __init__(self, *args, **kwargs):
        from integrations.models import DeviceGroup
        queryset = kwargs.get('queryset', DeviceGroup.objects.none())  # Empty queryset since we don't want to show options
        kwargs['queryset'] = queryset
        widget = DeviceGroupAutoCreateWidget()
        kwargs['widget'] = widget
        kwargs['required'] = False
        super().__init__(*args, **kwargs)


class DeviceGroupDisplayWidget(forms.Widget):
    """
    A widget that displays the device group name with a link to its manage page.
    """
    
    def render(self, name, value, attrs=None, renderer=None):
        if not value:
            return format_html('<div class="text-muted">No default device group set</div>')
        
        try:
            from integrations.models import DeviceGroup
            device_group = DeviceGroup.objects.get(id=value)
            manage_url = reverse('device_group_management_update', kwargs={'device_group_id': device_group.id})
            
            return format_html(
                '''
                <div class="device-group-display">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-layer-group me-2 text-primary"></i>
                        <div>
                            <strong>{device_group_name}</strong><br>
                            <small class="text-muted">Organization: {owner_name}</small><br>
                            <a href="{manage_url}" class="btn btn-sm btn-outline-primary mt-1">
                                <i class="fas fa-cog"></i> Manage Device Group
                            </a>
                        </div>
                    </div>
                </div>
                <input type="hidden" name="{name}" value="{value}">
                ''',
                device_group_name=device_group.name,
                owner_name=device_group.owner.name,
                manage_url=manage_url,
                name=name,
                value=value
            )
        except DeviceGroup.DoesNotExist:
            return format_html('<div class="text-muted">Device group not found</div>')
    
    def value_from_datadict(self, data, files, name):
        """Return the hidden input value to preserve the device group ID."""
        return data.get(name)
