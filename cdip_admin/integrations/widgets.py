from django import forms
from django.utils.html import format_html
from django.utils.safestring import mark_safe


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
        print(f"=== WIDGET RENDER DEBUG ===")
        print(f"Widget render called for field: {name}")
        print(f"Value: {value}")
        print(f"Attrs: {attrs}")
        
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
                queryset = field.queryset.all()
                for obj in queryset:
                    choices.append((str(obj.pk), str(obj)))
            except Exception as e:
                print(f"Error getting queryset: {e}")
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
                <div class="search-input-container mb-2">
                    <input type="text" 
                           class="form-control search-input" 
                           placeholder="Search destinations..." 
                           id="{widget_id}_search">
                </div>
                
                <div class="selected-items mb-2">
                    <label class="form-label">Selected Destinations:</label>
                    <div class="selected-list" id="{widget_id}_selected">
                        <!-- Selected items will be populated here -->
                    </div>
                </div>
                
                <div class="available-items">
                    <label class="form-label">Available Destinations:</label>
                    <div class="available-list" id="{widget_id}_available">
                        <!-- Available items will be populated here -->
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
        print(f"=== VALUE_FROM_DATADICT DEBUG ===")
        print(f"Field name: {name}")
        print(f"Data keys: {list(data.keys())}")
        
        values = []
        
        # Look for values with the pattern name_0, name_1, etc.
        i = 0
        while True:
            key = f"{name}_{i}"
            if key in data:
                values.append(data[key])
                print(f"Found {key}: {data[key]}")
                i += 1
            else:
                break
        
        # Also check for a single value with the name
        if name in data:
            values.append(data[name])
            print(f"Found {name}: {data[name]}")
        
        # Handle the case where field names might include UUIDs
        # Look for any keys that start with the field name
        for key in data.keys():
            if key.startswith(f"{name}_") and key not in [f"{name}_{i}" for i in range(len(values))]:
                # This might be a UUID-based field name
                values.append(data[key])
                print(f"Found UUID-based field {key}: {data[key]}")
        
        print(f"Final values: {values}")
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
