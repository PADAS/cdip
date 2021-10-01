from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0032_inboundintegrationconfiguration_provider'),
    ]

    operations = [
        migrations.RunSQL(
            sql="UPDATE integrations_inboundintegrationconfiguration SET provider = ii.slug FROM integrations_inboundintegrationtype ii WHERE type_id = ii.id AND provider = ''",
        ),
    ]
