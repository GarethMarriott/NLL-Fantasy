from django.contrib.admin import AdminSite
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.core.exceptions import ValidationError

from web.forms import ImportWeeklyStatsForm
from web.importers import import_weekly_stats_csv
from web.models import ImportRun


class FantasyAdminSite(AdminSite):
    site_header = "Fantasy Lacrosse Admin"
    site_title = "Fantasy Lacrosse Admin"
    index_title = "Admin"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "import-weekly-stats/",
                self.admin_view(self.import_weekly_stats_view),
                name="import-weekly-stats",
            ),
        ]
        return custom + urls

    def import_weekly_stats_view(self, request):
        if request.method == "POST":
            form = ImportWeeklyStatsForm(request.POST, request.FILES)
            if form.is_valid():
                f = form.cleaned_data["csv_file"]

                run = ImportRun.objects.create(
                    uploaded_by=request.user,
                    uploaded_file=f,
                    original_filename=getattr(f, "name", ""),
                    status=ImportRun.Status.PENDING,
                )

                run.status = ImportRun.Status.RUNNING
                run.started_at = timezone.now()
                run.save(update_fields=["status", "started_at"])

                try:
                    log_text, counters = import_weekly_stats_csv(run)
                    run.status = ImportRun.Status.SUCCESS
                    run.log = log_text
                    for k, v in counters.items():
                        setattr(run, k, v)
                    messages.success(request, "Import succeeded.")
                except ValidationError as e:
                    run.status = ImportRun.Status.FAILED
                    run.log = "\n".join(e.messages) if hasattr(e, "messages") else str(e)
                    messages.error(request, f"Import failed: {run.log}")
                except Exception as e:
                    run.status = ImportRun.Status.FAILED
                    run.log = f"Unexpected error: {type(e).__name__}: {e}"
                    messages.error(request, run.log)

                run.finished_at = timezone.now()
                run.save()

                return redirect(f"/admin/web/importrun/{run.id}/change/")
        else:
            form = ImportWeeklyStatsForm()

        context = dict(self.each_context(request), form=form, title="Import Weekly Stats CSV")
        return render(request, "admin/import_weekly_stats.html", context)
