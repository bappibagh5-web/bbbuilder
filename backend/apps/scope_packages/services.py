from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.analysis.models import ProjectIntelligenceApproval, ProjectIntelligenceSnapshot
from apps.projects.audit import record_event

from .models import ScopePackage, ScopePackageSource, ScopePackageVersion
from .taxonomy import CURRENT_RULE_VERSION, trades_for_entry


def _inclusion(entry):
    subject = entry.finding.subject.strip()
    return f"{subject}: {entry.effective_value}" if subject else entry.effective_value


@transaction.atomic
def generate_scope_packages(*, project, snapshot, actor):
    locked_project = type(project).objects.select_for_update().get(pk=project.pk)
    if not locked_project.is_active:
        raise ValidationError("Scope packages cannot be generated for an archived project.")
    snapshot = (
        ProjectIntelligenceSnapshot.objects.select_related("project")
        .prefetch_related("entries__finding")
        .get(pk=snapshot.pk)
    )
    if snapshot.project_id != locked_project.pk:
        raise ValidationError("Approved project information must belong to this project.")
    if not ProjectIntelligenceApproval.objects.filter(snapshot=snapshot).exists():
        raise ValidationError("Scope packages require approved project information.")

    groups = defaultdict(list)
    for entry in snapshot.entries.all():
        if entry.included_in_intelligence and entry.effective_value:
            for trade in trades_for_entry(entry):
                groups[(trade.key, trade.label)].append(entry)
    if not groups:
        raise ValidationError("Approved project information has no included scope content.")

    created = []
    existing = []
    for (trade_key, trade_category), entries in sorted(groups.items()):
        package = ScopePackage.objects.filter(
            project=locked_project,
            source_snapshot=snapshot,
            trade_key=trade_key,
            lifecycle=ScopePackage.Lifecycle.ACTIVE,
        ).first()
        if package:
            existing.append(package)
            continue
        package = ScopePackage.objects.create(
            organization=locked_project.organization,
            project=locked_project,
            source_snapshot=snapshot,
            trade_key=trade_key,
            trade_category=trade_category,
            generation_rule_version=CURRENT_RULE_VERSION,
            created_by=actor,
            updated_by=actor,
        )
        inclusions = list(dict.fromkeys(_inclusion(entry) for entry in entries))
        version = ScopePackageVersion.objects.create(
            package=package,
            version=1,
            title=f"{trade_category} Scope",
            description=(
                f"Draft generated deterministically from approved Project Information "
                f"Version {snapshot.version}."
            ),
            inclusions=inclusions,
            exclusions=[],
            clarifications=[],
            status=ScopePackageVersion.Status.DRAFT,
            created_by=actor,
        )
        ScopePackageSource.objects.bulk_create(
            [ScopePackageSource(package_version=version, snapshot_entry=entry) for entry in entries]
        )
        package.current_version = version
        package.save(update_fields=("current_version", "updated_at"))
        record_event(
            organization=package.organization,
            project=package.project,
            actor=actor,
            action_code="scope_package.generated",
            target=package,
            metadata={"snapshot_id": snapshot.pk, "version": 1},
        )
        created.append(package)

    legacy_packages = ScopePackage.objects.filter(
        project=locked_project,
        source_snapshot=snapshot,
        lifecycle=ScopePackage.Lifecycle.ACTIVE,
        generation_rule_version__lt=CURRENT_RULE_VERSION,
    ).select_related("current_version")
    for legacy in legacy_packages:
        if (
            legacy.current_version
            and legacy.current_version.version == 1
            and legacy.current_version.status == ScopePackageVersion.Status.DRAFT
            and legacy.versions.count() == 1
        ):
            legacy.lifecycle = ScopePackage.Lifecycle.SUPERSEDED
            legacy.updated_by = actor
            legacy.save(update_fields=("lifecycle", "updated_by", "updated_at"))
            record_event(
                organization=legacy.organization,
                project=legacy.project,
                actor=actor,
                action_code="scope_package.superseded",
                target=legacy,
                metadata={"replacement_rule_version": CURRENT_RULE_VERSION},
            )
    return created, existing


@transaction.atomic
def revise_scope_package(*, package, actor, values, mark_ready=False):
    package = ScopePackage.objects.select_for_update().select_related("project").get(pk=package.pk)
    if not package.project.is_active:
        raise ValidationError("Scope packages in an archived project cannot be changed.")
    current = package.current_version
    if current is None:
        raise ValidationError("Scope package has no current version.")
    if mark_ready and current.status == ScopePackageVersion.Status.READY:
        return current, False

    content = {
        "title": values.get("title", current.title),
        "description": values.get("description", current.description),
        "inclusions": values.get("inclusions", current.inclusions),
        "exclusions": values.get("exclusions", current.exclusions),
        "clarifications": values.get("clarifications", current.clarifications),
        "status": (
            ScopePackageVersion.Status.READY if mark_ready else ScopePackageVersion.Status.DRAFT
        ),
    }
    if not mark_ready and all(getattr(current, key) == value for key, value in content.items()):
        return current, False
    next_version = (
        ScopePackageVersion.objects.filter(package=package).aggregate(value=Max("version"))["value"]
        or 0
    ) + 1
    version = ScopePackageVersion.objects.create(
        package=package, version=next_version, created_by=actor, **content
    )
    ScopePackageSource.objects.bulk_create(
        [
            ScopePackageSource(package_version=version, snapshot_entry_id=source_id)
            for source_id in current.sources.values_list("snapshot_entry_id", flat=True)
        ]
    )
    package.current_version = version
    package.updated_by = actor
    package.save(update_fields=("current_version", "updated_by", "updated_at"))
    record_event(
        organization=package.organization,
        project=package.project,
        actor=actor,
        action_code="scope_package.ready" if mark_ready else "scope_package.updated",
        target=package,
        metadata={"version": version.version, "source_snapshot_id": package.source_snapshot_id},
    )
    return version, True
