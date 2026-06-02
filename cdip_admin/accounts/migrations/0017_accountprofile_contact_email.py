from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_alter_eula_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountprofile',
            name='contact_email',
            field=models.EmailField(
                blank=True,
                help_text='User-controlled contact email, independent of the auth provider email.',
                max_length=254,
                null=True,
            ),
        ),
    ]
