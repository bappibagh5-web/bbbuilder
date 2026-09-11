from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("analysis", "0004_alter_projectintelligencesnapshotentry_decision_and_more")]

    operations = [
        migrations.AlterField(
            model_name="analysisrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="queued",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="analysisrun",
            name="failure_code",
            field=models.CharField(
                blank=True,
                choices=[
                    ("source_not_verified", "Source not verified"),
                    ("pdf_not_indexed", "PDF not indexed"),
                    ("unsupported_document", "Unsupported document"),
                    ("ai_configuration_missing", "AI configuration missing"),
                    ("provider_unavailable", "Provider unavailable"),
                    ("provider_rate_limited", "Provider rate limited"),
                    ("provider_timeout", "Provider timeout"),
                    ("invalid_structured_response", "Invalid structured response"),
                    ("page_render_failed", "Page render failed"),
                    ("analysis_failed", "Analysis failed"),
                    ("worker_lost", "Worker lost"),
                    ("analysis_cancelled", "Analysis cancelled"),
                ],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="analysistaskrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="queued",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="analysistaskrun",
            name="error_code",
            field=models.CharField(
                blank=True,
                choices=[
                    ("source_not_verified", "Source not verified"),
                    ("pdf_not_indexed", "PDF not indexed"),
                    ("unsupported_document", "Unsupported document"),
                    ("ai_configuration_missing", "AI configuration missing"),
                    ("provider_unavailable", "Provider unavailable"),
                    ("provider_rate_limited", "Provider rate limited"),
                    ("provider_timeout", "Provider timeout"),
                    ("invalid_structured_response", "Invalid structured response"),
                    ("page_render_failed", "Page render failed"),
                    ("analysis_failed", "Analysis failed"),
                    ("worker_lost", "Worker lost"),
                    ("analysis_cancelled", "Analysis cancelled"),
                ],
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="analysistaskrun",
            name="reused_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reuse_successors",
                to="analysis.analysistaskrun",
            ),
        ),
    ]
