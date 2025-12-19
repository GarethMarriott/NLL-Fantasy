from django.contrib import admin
from .models import Player, Week, PlayerWeekStat


class PlayerWeekStatInline(admin.TabularInline):
    model = PlayerWeekStat
    extra = 0
    autocomplete_fields = ["week"]
    fields = (
        "week",
        "goals",
        "assists",
        "points",
        "penalty_minutes",
        "powerplay_goals",
        "powerplay_assists",
        "shorthanded_goals",
        "loose_balls",
        "turnovers",
        "caused_turnovers",
        "blocked_shots",
        "shots_on_goal",
        "faceoff_percentage",
        "source_file",
        "updated_at",
    )
    readonly_fields = ("updated_at",)
    ordering = ("week__season", "week__week_number")


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("last_name", "first_name", "number", "position", "active", "external_id")
    list_filter = ("position", "active")
    search_fields = ("first_name", "last_name", "external_id")
    ordering = ("last_name", "first_name")
    inlines = [PlayerWeekStatInline]


class PlayerWeekStatWeekInline(admin.TabularInline):
    model = PlayerWeekStat
    extra = 0
    autocomplete_fields = ["player"]
    fields = (
        "player",
        "goals",
        "assists",
        "points",
        "penalty_minutes",
        "powerplay_goals",
        "powerplay_assists",
        "shorthanded_goals",
        "loose_balls",
        "turnovers",
        "caused_turnovers",
        "blocked_shots",
        "shots_on_goal",
        "faceoff_percentage",
        "source_file",
        "updated_at",
    )
    readonly_fields = ("updated_at",)
    ordering = ("player__last_name", "player__first_name")


@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ("season", "week_number", "start_date", "end_date")
    list_filter = ("season",)
    search_fields = ("season", "week_number")
    ordering = ("-season", "week_number")
    inlines = [PlayerWeekStatWeekInline]


@admin.register(PlayerWeekStat)
class PlayerWeekStatAdmin(admin.ModelAdmin):
    list_display = (
        "player",
        "week",
        "goals",
        "assists",
        "points",
        "penalty_minutes",
        "powerplay_goals",
        "powerplay_assists",
        "shorthanded_goals",
        "loose_balls",
        "turnovers",
        "caused_turnovers",
        "blocked_shots",
        "shots_on_goal",
        "faceoff_percentage",
        "source_file",
        "updated_at",
    )
    list_filter = ("week__season", "week__week_number", "player__position")
    search_fields = ("player__first_name", "player__last_name", "player__external_id", "source_file")
    autocomplete_fields = ("player", "week")
    ordering = ("-week__season", "-week__week_number", "player__last_name", "player__first_name")