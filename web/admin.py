from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Player, Week, Game, PlayerGameStat
from .models import ImportRun
from .models import FantasyTeamOwner, ChatMessage, Team, League, Roster, WaiverClaim, Draft, DraftPosition, DraftPick, BugReport
from .forms import ImportWeeklyStatsForm, ImportTeamsForm
from .importers import import_weekly_stats_csv, import_teams_csv
from django.contrib import admin
from .admin_site import FantasyAdminSite

admin_site = FantasyAdminSite(name="fantasy_admin")


@admin.register(Player, site=admin_site)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "number", "position", "active", "external_id")
    list_filter = ("position", "active")
    search_fields = ("first_name", "last_name", "external_id")
    ordering = ("last_name", "first_name")


class PlayerGameStatInline(admin.TabularInline):
    model = PlayerGameStat
    extra = 0
@admin.register(PlayerGameStat, site=admin_site)
class PlayerGameStatAdmin(admin.ModelAdmin):
    list_display = (
        "player",
        "game",
        "goals",
        "assists",
        "points",
        "loose_balls",
        "turnovers",
        "caused_turnovers",
        "blocked_shots",
        "wins",
        "saves",
        "goals_against",
        "updated_at",
    )
    search_fields = ("player__last_name", "player__first_name", "game__week__season", "game__week__week_number")
    list_filter = ("game__week__season", "game__week__week_number", "player__position")
    ordering = ("-game__week__season", "-game__week__week_number", "player__last_name")


@admin.register(Week, site=admin_site)
class WeekAdmin(admin.ModelAdmin):
    list_display = ("season", "week_number", "start_date", "end_date")
    list_filter = ("season",)
    search_fields = ("season", "week_number")
    ordering = ("-season", "week_number")


@admin.register(Game, site=admin_site)
class GameAdmin(admin.ModelAdmin):
    list_display = ("week", "date", "home_team", "away_team", "location")
    list_filter = ("week__season", "date")
    search_fields = ("home_team", "away_team", "location")
    ordering = ("-date", "home_team")


@admin.register(ImportRun, site=admin_site)
class ImportRunAdmin(admin.ModelAdmin):
    change_list_template = "admin/web/importrun/change_list.html"
    list_display = ("created_at", "status", "original_filename", "uploaded_by")
    list_filter = ("status", "created_at")
    readonly_fields = (
        "status",
        "uploaded_by",
        "original_filename",
        "uploaded_file",
        "players_created",
        "players_updated",
        "weeks_created",
        "weeks_updated",
        "stats_created",
        "stats_updated",
        "log",
        "started_at",
        "finished_at",
        "created_at",
    )
    search_fields = ("original_filename", "log")
    actions = ["delete_imported_stats"]

    def has_add_permission(self, request):
        # prevent creating ImportRun manually; use the upload page instead
        return False

    def delete_imported_stats(self, request, queryset):
        """Admin action: delete PlayerWeekStat rows imported by selected ImportRun(s).

        Matches `PlayerWeekStat.source_file` against the ImportRun `original_filename`
        and the uploaded_file name (fallback) since the importer sets `source_file`
        to one of those values.
        """
        total_deleted = 0
        for run in queryset:
            candidates = []
            if run.original_filename:
                candidates.append(run.original_filename)
            if run.uploaded_file and getattr(run.uploaded_file, "name", None):
                candidates.append(run.uploaded_file.name)
            if not candidates:
                continue
            qs = PlayerWeekStat.objects.filter(source_file__in=candidates)
            count = qs.count()
            if count:
                qs.delete()
                total_deleted += count

        if total_deleted:
            messages.success(request, f"Deleted {total_deleted} imported stat rows.")
        else:
            messages.info(request, "No imported stat rows found for the selected imports.")

    delete_imported_stats.short_description = "Delete PlayerWeeklyStats created by this import"


# Add a custom "Upload CSV" view under the admin
class ImportToolsAdminSiteMixin:
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "import-weekly-stats/",
                self.admin_site.admin_view(self.import_weekly_stats_view),
                name="import-weekly-stats",
            ),
            path(
                "import-teams/",
                self.admin_site.admin_view(self.import_teams_view),
                name="import-teams",
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

                # Run import
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

                # Redirect to the ImportRun record
                return redirect(f"/admin/web/importrun/{run.id}/change/")
        else:
            form = ImportWeeklyStatsForm()

        context = dict(
            self.admin_site.each_context(request),
            form=form,
            title="Import Weekly Stats CSV",
        )
        return render(request, "admin/import_weekly_stats.html", context)


def admin_import_teams_view(request):
    """Standalone admin view for importing teams via CSV (wrapped in URLconf with admin_view)."""
    if request.method == "POST":
        form = ImportTeamsForm(request.POST, request.FILES)
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
                log_text, counters = import_teams_csv(run)
                run.status = ImportRun.Status.SUCCESS
                run.log = log_text

                run.players_created = counters.get("players_created", 0)
                run.players_updated = counters.get("players_updated", 0)
                run.save()

                messages.success(request, "Teams import succeeded.")
            except ValidationError as e:
                run.status = ImportRun.Status.FAILED
                run.log = "\n".join(e.messages) if hasattr(e, "messages") else str(e)
                run.save()
                messages.error(request, f"Import failed: {run.log}")
            except Exception as e:
                run.status = ImportRun.Status.FAILED
                run.log = f"Unexpected error: {type(e).__name__}: {e}"
                run.save()
                messages.error(request, run.log)

            return redirect(f"/admin/web/importrun/{run.id}/change/")
    else:
        form = ImportTeamsForm()

    context = dict(
        admin_site.each_context(request),
        form=form,
        title="Import Teams CSV",
    )
    return render(request, "admin/import_weekly_stats.html", context)

    def import_teams_view(self, request):
        if request.method == "POST":
            form = ImportTeamsForm(request.POST, request.FILES)
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
                    log_text, counters = import_teams_csv(run)
                    run.status = ImportRun.Status.SUCCESS
                    run.log = log_text

                    # store player counters where available
                    run.players_created = counters.get("players_created", 0)
                    run.players_updated = counters.get("players_updated", 0)
                    run.weeks_created = 0
                    run.weeks_updated = 0
                    run.stats_created = 0
                    run.stats_updated = 0

                    messages.success(request, "Teams import succeeded.")
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
            form = ImportTeamsForm()

        context = dict(
            self.admin_site.each_context(request),
            form=form,
            title="Import Teams CSV",
        )
        return render(request, "admin/import_weekly_stats.html", context)


# Monkey-patch the existing Player/Week/Stat admins to include the extra URL
# Easiest approach: subclass AdminSite is overkill; so we attach mixin to one admin.
# We'll attach to ImportRunAdmin by re-registering it is messy; instead we extend admin.site directly.
# The clean way: create a custom AdminSite. MVP shortcut below:

# Add URL to the global admin site by subclassing AdminSite (clean MVP approach)
from django.contrib.admin import AdminSite


class FantasyAdminSite(ImportToolsAdminSiteMixin, AdminSite):
    site_header = "Fantasy Lacrosse Admin"
    site_title = "Fantasy Lacrosse Admin"
    index_title = "Admin"


# IMPORTANT:
# If you want the clean/custom admin site, you must switch to it in config/urls.py.


@admin.register(League, site=admin_site)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "commissioner", "team_count", "max_teams", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "commissioner__username")
    readonly_fields = ("created_at", "updated_at", "unique_id")
    ordering = ("-created_at",)
    
    fieldsets = (
        ("Basic Info", {
            'fields': ('name', 'commissioner', 'description', 'unique_id', 'is_public', 'is_active')
        }),
        ("Team Settings", {
            'fields': ('max_teams', 'roster_size')
        }),
        ("Playoff Settings", {
            'fields': ('playoff_weeks', 'playoff_teams', 'playoff_reseed')
        }),
        ("Scoring Settings", {
            'fields': ('scoring_goals', 'scoring_assists', 'scoring_loose_balls', 'scoring_caused_turnovers', 'scoring_blocked_shots', 'scoring_turnovers', 'scoring_goalie_wins', 'scoring_goalie_saves', 'scoring_goalie_goals_against', 'scoring_goalie_goals', 'scoring_goalie_assists')
        }),
        ("Multi-Game Week Scoring", {
            'fields': ('multigame_scoring',)
        }),
        ("Waiver Settings", {
            'fields': ('use_waivers',)
        }),
        ("Timestamps", {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def team_count(self, obj):
        return obj.teams.count()
    team_count.short_description = "Teams"


@admin.register(Team, site=admin_site)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "league", "created_at")
    list_filter = ("league",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(FantasyTeamOwner, site=admin_site)
class FantasyTeamOwnerAdmin(admin.ModelAdmin):
    list_display = ("user", "team", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "team__name")
    autocomplete_fields = ["team"]
    raw_id_fields = ["user"]
    ordering = ("team__name",)


@admin.register(ChatMessage, site=admin_site)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "league", "message_type", "message_preview", "created_at")
    list_filter = ("message_type", "league", "created_at")
    search_fields = ("message", "sender__username")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    
    def message_preview(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = "Message"


@admin.register(Roster, site=admin_site)
class RosterAdmin(admin.ModelAdmin):
    list_display = ("player", "team", "league", "added_date")
    list_filter = ("league", "team", "added_date")
    search_fields = ("player__first_name", "player__last_name", "team__name")
    autocomplete_fields = ["player", "team"]
    ordering = ("league", "team", "player")
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('player', 'team', 'league')

@admin.register(WaiverClaim, site=admin_site)
class WaiverClaimAdmin(admin.ModelAdmin):
    list_display = ("team", "player_to_add", "player_to_drop", "week", "priority", "status", "created_at")
    list_filter = ("status", "league", "week", "created_at")
    search_fields = ("team__name", "player_to_add__first_name", "player_to_add__last_name")
    autocomplete_fields = ["team", "player_to_add", "player_to_drop", "week"]
    readonly_fields = ("created_at", "updated_at", "processed_at")
    ordering = ("week", "priority", "created_at")
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('team', 'player_to_add', 'player_to_drop', 'week', 'league')


@admin.register(Draft, site=admin_site)
class DraftAdmin(admin.ModelAdmin):
    list_display = ("league", "draft_order_type", "draft_style", "is_active", "completed", "current_round", "current_pick", "started_at")
    list_filter = ("is_active", "completed", "draft_order_type", "draft_style", "created_at")
    search_fields = ("league__name",)
    readonly_fields = ("created_at", "started_at", "completed_at")
    ordering = ("-created_at",)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('league')


@admin.register(DraftPosition, site=admin_site)
class DraftPositionAdmin(admin.ModelAdmin):
    list_display = ("draft", "team", "position")
    list_filter = ("draft",)
    search_fields = ("team__name", "draft__league__name")
    ordering = ("draft", "position")
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('draft', 'team')


@admin.register(DraftPick, site=admin_site)
class DraftPickAdmin(admin.ModelAdmin):
    list_display = ("draft", "round", "pick_number", "overall_pick", "team", "player", "timestamp")
    list_filter = ("draft", "round")
    search_fields = ("team__name", "player__first_name", "player__last_name", "draft__league__name")
    autocomplete_fields = ["team", "player"]
    readonly_fields = ("timestamp",)
    ordering = ("draft", "overall_pick")
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('draft', 'team', 'player')


@admin.register(BugReport, site=admin_site)
class BugReportAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "priority", "reporter", "created_at")
    list_filter = ("status", "priority", "created_at")
    search_fields = ("title", "description", "page_url", "reporter__username")
    readonly_fields = ("created_at", "updated_at", "browser_info", "error_message")
    fieldsets = (
        ("Report Details", {
            "fields": ("title", "description", "priority", "status", "reporter", "page_url")
        }),
        ("Technical Information", {
            "fields": ("browser_info", "error_message"),
            "classes": ("collapse",)
        }),
        ("Admin Notes", {
            "fields": ("admin_notes",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    ordering = ("-created_at",)