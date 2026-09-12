from django.db import migrations, models
import django.db.models.deletion


TRADE_CHOICES = [
    ("av", "AV"), ("backing-blocking", "Backing / Blocking"),
    ("civil-site", "Civil / Site Work"), ("closeout", "Closeout"),
    ("demolition", "Demolition"), ("doors-frames-hardware", "Doors / Frames / Hardware"),
    ("drywall", "Drywall"), ("electrical-power", "Electrical Power"),
    ("fire-alarm", "Fire Alarm"), ("fire-protection", "Fire Protection / Sprinklers"),
    ("flooring", "Flooring"), ("glazing-storefront", "Glazing / Storefront"),
    ("hvac-mechanical", "HVAC / Mechanical"), ("lighting", "Lighting"),
    ("low-voltage-data", "Low Voltage / Data"), ("millwork", "Millwork"),
    ("miscellaneous-metals", "Miscellaneous Metals"),
    ("mudding-taping", "Mudding & Taping"),
    ("painting-finishes", "Painting / Finishes"), ("plumbing", "Plumbing"),
    ("roofing", "Roofing"), ("security", "Security"), ("signage", "Signage"),
    ("specialties", "Specialties"), ("steel-stud-framing", "Steel Stud Framing"),
    ("structural", "Structural"), ("act-ceilings", "T-Bar / ACT Ceilings"),
]


def bind_candidates_to_current_versions(apps, schema_editor):
    Candidate = apps.get_model("contractors", "ScopeContractorCandidate")
    DiscoveryRequest = apps.get_model("contractors", "DiscoveryRequest")
    for candidate in Candidate.objects.select_related("scope_package").iterator():
        request = (
            DiscoveryRequest.objects.filter(
                project_id=candidate.project_id,
                scope_package_id=candidate.scope_package_id,
                requested_at__lte=candidate.created_at,
            )
            .order_by("-requested_at", "-id")
            .first()
        )
        candidate.scope_version_id = (
            request.scope_version_id if request else candidate.scope_package.current_version_id
        )
        candidate.save(update_fields=("scope_version",))


class Migration(migrations.Migration):
    dependencies = [("contractors", "0002_alter_contact_options_and_more")]

    operations = [
        migrations.AddField(
            model_name="company", name="latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="company", name="longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="discoveryrequest", name="center_latitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="discoveryrequest", name="center_longitude",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name="discoveryrequest", name="center_reference",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="discoveryrequest", name="project_location_key",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="discoveryrequest", name="radius_miles",
            field=models.PositiveIntegerField(default=200),
        ),
        migrations.AddField(
            model_name="scopecontractorcandidate", name="scope_version",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="contractor_candidates", to="scope_packages.scopepackageversion",
            ),
        ),
        migrations.RunPython(bind_candidates_to_current_versions, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="scopecontractorcandidate", name="scope_version",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="contractor_candidates", to="scope_packages.scopepackageversion",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="scopecontractorcandidate", name="contractor_unique_scope_company",
        ),
        migrations.AddConstraint(
            model_name="scopecontractorcandidate",
            constraint=models.UniqueConstraint(
                fields=("project", "scope_version", "company"),
                name="contractor_unique_scope_version_company",
            ),
        ),
        migrations.AlterField(
            model_name="tradecapability", name="trade_key",
            field=models.CharField(choices=TRADE_CHOICES, max_length=100),
        ),
        migrations.AlterField(
            model_name="discoveryrequest", name="trade_key",
            field=models.CharField(choices=TRADE_CHOICES, max_length=100),
        ),
    ]
