# Generated by Django 3.1 on 2021-03-26 21:28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0005_auto_20210210_1259'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE accounts_accountprofile_organizations RENAME TO accounts_accountprofileorganization',
                    reverse_sql= 'ALTER TABLE accounts_accountprofileorganization RENAME TO accounts_accountprofile_organizations'
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='AccountProfileOrganization',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('role', models.CharField(max_length=200)),
                        ('account_profile',
                         models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.accountprofile')),
                        ('organization',
                         models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='organizations.organization')),
                    ],
                ),
                migrations.AlterField(
                    model_name='accountprofile',
                    name='organizations',
                    field=models.ManyToManyField(through='accounts.AccountProfileOrganization',
                                                 to='organizations.Organization'),
                ),
                ]
            ),
        migrations.AddField(
            model_name='AccountProfileOrganization',
            name='role',
            field=models.CharField(max_length=200, default='viewer'),
        ),
    ]

