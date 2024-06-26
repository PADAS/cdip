from django import forms
import json
from django_filters.widgets import BooleanWidget

import logging

logger = logging.getLogger(__name__)


class FormattedJsonFieldWidget(forms.widgets.Textarea):

    template_name = "widgets/formatted_json/formatted_json.html"

    def __init__(self, attrs=None):
        # Use slightly better defaults than HTML's 20x2 box
        default_attrs = {"cols": "80", "rows": "20"}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def format_value(self, value):
        try:
            value = json.dumps(json.loads(value), indent=2, sort_keys=True)
            # these lines will try to adjust size of TextArea to fit to content
            row_lengths = [len(r) for r in value.split("\n")]
            self.attrs["rows"] = min(max(len(row_lengths) + 2, 10), 30)
            return value
        except Exception as e:
            logger.warning("Failed to format json.")

        return super().format_value(value)

    class Media:
        # Remember, these are either paths in /static/ or absolute URLs.
        css = {"all": ("widgets/formatted_json/formatted_json.css",)}


class PeekabooTextInput(forms.widgets.TextInput):

    input_type = "password"
    template_name = "widgets/peekaboo/peekaboo.html"
    readonly = ""

    class Media:
        css = {"all": ("widgets/peekaboo/peekaboo.css",)}
        js = (
            "widgets/peekaboo/peekaboo.js",
            "https://kit.fontawesome.com/0f5032f73b.js",
        )

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["readonly"] = self.readonly
        return context


class ReadonlyPeekabooTextInput(PeekabooTextInput):

    readonly = "readonly"


class CustomBooleanWidget(BooleanWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.choices = (("", "All Statuses"), ("true", "Enabled"), ("false", "Not Enabled"))

class HasErrorBooleanWidget(BooleanWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.choices = (("", "All"), ("true", "Has Error"), ("false", "No Error"))