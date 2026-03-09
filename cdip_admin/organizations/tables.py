import django_tables2 as tables

from .models import Organization


class OrganizationTable(tables.Table):
    actions = tables.TemplateColumn(
        template_code='''
        <button type="button" class="btn btn-outline-secondary btn-sm"
            hx-get="{% url 'organizations_update' organization_id=record.id %}"
            hx-target="#slide-panel-body"
            hx-swap="innerHTML"
            onclick="history.replaceState(null, '', location.pathname + location.search + '#edit={{ record.id }}'); document.body.dispatchEvent(new Event('openPanel'));">Edit</button>
        ''',
        orderable=False,
        verbose_name="",
    )
    name = tables.Column(linkify=lambda record: record.get_absolute_url())
    description = tables.Column()

    class Meta:
        model = Organization
        template_name = "django_tables2/bootstrap4.html"
        fields = ()
        sequence = ("actions", "name", "description")
        attrs = {"class": "table table-hover", "id": "organization-table"}
        order_by = "name"
