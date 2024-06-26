# Generated by Django 3.2.15 on 2023-08-08 21:06

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0085_alter_gunditrace_related_to'),
        ('deployments', '0004_alter_dispatcherdeployment_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dispatcherdeployment',
            name='integration',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dispatcher_by_integration', to='integrations.integration', verbose_name='Destination Integration'),
        ),
        migrations.AlterField(
            model_name='dispatcherdeployment',
            name='legacy_integration',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dispatcher_by_outbound', to='integrations.outboundintegrationconfiguration', verbose_name='Legacy Outbound Integration'),
        ),
    ]
