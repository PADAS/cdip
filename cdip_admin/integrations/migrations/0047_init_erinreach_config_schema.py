# Generated by Django 3.2 on 2022-10-13 19:09

import json
from django.db import migrations


ER_INREACH_CONFIG_SCHEMA = json.loads(
    '''{
  "$id": "http://example.com/example.json",
  "type": "object",
  "title": "InReach Bridge Integration Schema",
  "$schema": "https://json-schema.org/draft/2019-09/schema",
  "default": {},
  "examples": [
    {
      "er_site": "cdip-er.pamdas.org",
      "er_token": "fasfoiu3ia0fsui30f9ajiofa2",
      "inreach_url": "https://eur-enterprise.inreach.garmin.com",
      "inreach_password": "some-ipc-password",
      "inreach_username": "some-ipc-username",
      "er_source_provider": "my-inreach",
      "append_recipients_to_message": true
    }
  ],
  "required": [
    "er_site",
    "er_source_provider",
    "er_token",
    "inreach_password",
    "inreach_url",
    "inreach_username"
  ],
  "properties": {
    "er_site": {
      "type": "string",
      "title": "EarthRanger site",
      "default": "",
      "examples": [
        "cdip-er.pamdas.org"
      ],
      "description": "Hostname for your EarthRanger site"
    },
    "er_token": {
      "type": "string",
      "title": "EarthRanger Authorization Token",
      "default": "",
      "examples": [
        "gbk3io2su90afsifop308a903ajfaf90390ajfa"
      ]
    },
    "inreach_url": {
      "type": "string",
      "description": "The Inbound IPC URL for your InReach account",
      "title": "InReach Inbound IPC URL",
      "format": "url",
      "default": "",
      "examples": [
        "https://eur-enterprise.inreach.garmin.com"
      ]
    },
    "inreach_password": {
      "type": "string",
      "title": " nReach Inbound IPC password",
      "default": "",
      "examples": [
        "some-fancy-password"
      ]
    },
    "inreach_username": {
      "type": "string",
      "title": "InReach Inbound IPC username",
      "default": "",
      "examples": [
        "my-ipc-username"
      ]
    },
    "er_source_provider": {
      "type": "string",
      "title": "EarthRanger Source Provider key",
      "default": "",
      "examples": [
        "test-inreach"
      ]
    },
    "append_recipients_to_message": {
      "type": "boolean",
      "description": "If this is true, InReach message recipient address will be appended to message text as it appears in EarthRanger",
      "title": "Append recipient list to messages",
      "default": false,
      "examples": [
        true
      ]
    }
  }
}
'''
)


def ensure_er_inreach_config_schema(app_registry, schema_editor):

    db_alias = schema_editor.connection.alias

    BridgeIntegrationType = app_registry.get_model('integrations', 'BridgeIntegrationType')

    BridgeIntegrationType.objects.using(db_alias).update_or_create(
        slug='er_inreach',
        defaults={
            'name': 'ER+InReach',
            'configuration_schema': ER_INREACH_CONFIG_SCHEMA
        }

    )


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0046_bridge_config_schema'),
    ]

    operations = [

        migrations.RunPython(ensure_er_inreach_config_schema, reverse_code=migrations.RunPython.noop)
    ]
