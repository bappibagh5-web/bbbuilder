from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("scope_packages", "0004_scopeitem_responsibility")]

    operations = [
        migrations.AddField(
            model_name="scopepackage",
            name="plan_fingerprint",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="scopeitem",
            name="coordination_required",
            field=models.BooleanField(default=False),
        ),
    ]
