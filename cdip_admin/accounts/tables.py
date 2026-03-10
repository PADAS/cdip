import django_tables2 as tables
from django.contrib.auth.models import User


class AccountTable(tables.Table):
    actions = tables.TemplateColumn(
        template_code='''
        <button type="button" class="btn btn-outline-secondary btn-sm"
            hx-get="{% url 'account_update' user_id=record.id %}"
            hx-target="#slide-panel-body"
            hx-swap="innerHTML"
            onclick="history.replaceState(null, '', location.pathname + location.search + '#edit={{ record.id }}'); document.body.dispatchEvent(new Event('openPanel'));">Edit</button>
        ''',
        orderable=False,
        verbose_name="",
    )
    name = tables.Column(empty_values=(), verbose_name="Name", order_by=("last_name", "first_name"))
    email = tables.Column(accessor="email", verbose_name="Email")
    organizations = tables.Column(empty_values=(), verbose_name="Organizations", orderable=False)

    def render_name(self, record):
        return f"{record.last_name}, {record.first_name}"

    def render_organizations(self, record):
        if hasattr(record, "accountprofile"):
            orgs = record.accountprofile.organizations.all()
            return ", ".join(org.name for org in orgs)
        return ""

    class Meta:
        model = User
        template_name = "django_tables2/bootstrap4.html"
        fields = ()
        sequence = ("actions", "name", "email", "organizations")
        attrs = {"class": "table table-hover", "id": "account-table"}
        order_by = "last_name"
