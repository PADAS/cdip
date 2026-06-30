from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deployments', '0008_rename_topic_path_dispatcherdeployment_topic_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispatcherdeployment',
            name='failure_reason',
            field=models.CharField(
                blank=True,
                choices=[
                    ('quota_exhausted', 'Quota Exhausted'),
                    ('transient', 'Transient Error'),
                    ('config_error', 'Configuration Error'),
                    ('unknown', 'Unknown'),
                ],
                default='',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='dispatcherdeployment',
            name='last_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='dispatcherdeployment',
            name='attempt_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='dispatcherdeployment',
            name='last_attempt_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
