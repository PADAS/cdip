from django_jsonform.widgets import JSONFormWidget


class DynamicFormWidget(JSONFormWidget):
    def render(self, name, value, attrs=None, renderer=None):
        return super().render(name, value, attrs, renderer)
