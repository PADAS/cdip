# Generated by Django 3.1 on 2021-02-16 17:03
import json

from django.db import migrations, models

from integrations.models import DeviceState


class Migration(migrations.Migration):
    def forward_data_migration(apps, schema):
        for state in DeviceState.objects.all():
            try:
                state.state = json.loads(state.end_state)
            except json.decoder.JSONDecodeError as e:
                state.state = dict(value=str(state.end_state))
            state.save()

    dependencies = [
        ("integrations", "0020_auto_20210216_1703"),
    ]

    operations = [
        migrations.RunPython(
            code=forward_data_migration, reverse_code=migrations.RunPython.noop
        )
    ]
