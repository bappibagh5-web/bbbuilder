import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0001_initial'),
        ('prospecting', '0004_prospectlistentry_is_active_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='prospectsequencestep',
            name='label',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='prospectsequencestepversion',
            name='label',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.CreateModel(
            name='ProspectEmailTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=180)),
                ('category', models.CharField(blank=True, max_length=100)),
                ('subject', models.CharField(max_length=255)),
                ('body', models.TextField()),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_prospect_email_templates', to=settings.AUTH_USER_MODEL)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prospect_email_templates', to='organizations.organization')),
                ('updated_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='updated_prospect_email_templates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('name', 'id'),
                'constraints': [models.UniqueConstraint(fields=('organization', 'name'), name='prospecting_unique_email_template_name')],
            },
        ),
    ]
