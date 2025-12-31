from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from web.models import ImportRun
from web.importers import import_teams_csv


class Command(BaseCommand):
    help = "Re-run a teams import from an existing ImportRun to (re)assign players to teams."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, help="ImportRun id to re-run. If omitted, uses the latest run.")

    def handle(self, *args, **options):
        run_id = options.get("run_id")
        if run_id:
            try:
                run = ImportRun.objects.get(id=run_id)
            except ImportRun.DoesNotExist:
                raise CommandError(f"ImportRun with id={run_id} not found")
        else:
            run = ImportRun.objects.filter().order_by("-created_at").first()
            if not run:
                raise CommandError("No ImportRun records found")

        self.stdout.write(f"Re-running teams import for ImportRun id={run.id} (file={run.original_filename or getattr(run.uploaded_file,'name',None)})")

        try:
            log_text, counters = import_teams_csv(run)
            run.status = ImportRun.Status.SUCCESS
            run.log = (run.log or "") + "\nReimported:\n" + log_text
            run.players_created = counters.get("players_created", 0)
            run.players_updated = counters.get("players_updated", 0)
            run.save()
            self.stdout.write(self.style.SUCCESS("Reimport completed: " + log_text))
        except ValidationError as e:
            run.status = ImportRun.Status.FAILED
            run.log = (run.log or "") + "\nReimport failed:\n" + ("\n".join(e.messages) if hasattr(e, "messages") else str(e))
            run.save()
            raise CommandError("ValidationError: " + run.log)
        except Exception as e:
            run.status = ImportRun.Status.FAILED
            run.log = (run.log or "") + "\nReimport error:\n" + f"{type(e).__name__}: {e}"
            run.save()
            raise CommandError(f"Unexpected error: {type(e).__name__}: {e}")
