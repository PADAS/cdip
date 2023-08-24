# Generated by Django 3.2.15 on 2023-07-19 15:50

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0085_alter_gunditrace_related_to'),
        ('deployments', '0002_dispatcherdeployment_status_details'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dispatcherdeployment',
            name='legacy_integration',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='dispatcher_by_outbound', to='integrations.outboundintegrationconfiguration', verbose_name='Legacy Outbound Integration'),
        ),
    ]