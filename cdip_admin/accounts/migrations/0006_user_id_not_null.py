# Generated by Django 3.1 on 2021-05-11 22:35

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

sentinel_user_username = "sentinel-user"

CREATE_SENTINEL_USER = f"""
insert into auth_user(username, password, is_superuser, first_name, last_name, email, is_staff, is_active, date_joined, last_login) values (
'{sentinel_user_username}', '8hgaeio4$im', false, 'Sentinel', 'Sentinel', 'sentinel-user@sintegrate.org', false, false, current_timestamp, current_timestamp) on conflict do nothing;
"""

SET_NULLED_USER_IDS = f"""
 update accounts_accountprofile ap set user_id = au.id from auth_user au where au.username='{sentinel_user_username}' and ap.user_id is null;
"""

ALTER_USER_ID_SET_NOT_NULL = """
alter table accounts_accountprofile alter column user_id set not null;
"""


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0005_add_user_id_and_mapping"),
    ]

    operations = [
        migrations.RunSQL(
            "SET CONSTRAINTS ALL DEFERRED", reverse_sql="SET CONSTRAINTS ALL IMMEDIATE"
        ),
        migrations.RunSQL(CREATE_SENTINEL_USER, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(SET_NULLED_USER_IDS, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(
            ALTER_USER_ID_SET_NOT_NULL, reverse_sql=migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            "SET CONSTRAINTS ALL IMMEDIATE", reverse_sql="SET CONSTRAINTS ALL DEFERRED"
        ),
    ]
