from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings


class League(models.Model):
    """Fantasy league that contains multiple teams"""
    name = models.CharField(max_length=100)
    commissioner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='leagues_as_commissioner',
        help_text="User who created and manages the league"
    )
    description = models.TextField(blank=True)
    max_teams = models.PositiveSmallIntegerField(default=12, help_text="Maximum number of teams allowed")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} (by {self.commissioner.username})"


class Team(models.Model):
    name = models.CharField(max_length=100)
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name='teams',
        null=True,
        blank=True,
        help_text="The league this team belongs to"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'league'],
                name='unique_team_name_per_league'
            )
        ]

    def __str__(self) -> str:
        if self.league:
            return f"{self.name} ({self.league.name})"
        return self.name


class Player(models.Model):
    class Position(models.TextChoices):
        OFFENCE = "O", "Offence"
        DEFENCE = "D", "Defence"
        TRANSITION = "T", "Transition"
        GOALIE = "G", "Goalie"

    number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(99)],
        help_text="Jersey number (0-99). Not required to be unique.",
        null=True,
        blank=True,
    )

    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, null=True, blank=True)
    last_name = models.CharField(max_length=50)

    # Optional team association
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="players",
    )

    position = models.CharField(max_length=1, choices=Position.choices)

    # Optional assigned side for fantasy lineup (e.g., Transition slotted as Offence or Defence)
    assigned_side = models.CharField(
        max_length=1,
        choices=Position.choices,
        null=True,
        blank=True,
        help_text="Override for lineup slot (use O or D for Transition players)",
    )

    external_id = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        help_text="Unique ID from your source data (recommended for imports).",
    )

    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["position"]),
            models.Index(fields=["external_id"]),
        ]
        ordering = ["last_name", "first_name", "id"]

    def __str__(self) -> str:
        middle = f" {self.middle_name[0]}." if self.middle_name else ""
        num = f" #{self.number}" if self.number is not None else ""
        return f"{self.last_name}, {self.first_name}{middle}{num}"


class Week(models.Model):
    season = models.PositiveSmallIntegerField(help_text="e.g., 2026")
    week_number = models.PositiveSmallIntegerField(help_text="1..N within a season")

    start_date = models.DateField()
    end_date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["season", "week_number"], name="uniq_week_per_season"
            ),
        ]
        indexes = [
            models.Index(fields=["season", "week_number"]),
            models.Index(fields=["start_date", "end_date"]),
        ]
        ordering = ["-season", "week_number"]

    def __str__(self) -> str:
        return f"{self.season} - Week {self.week_number} ({self.start_date} to {self.end_date})"


class PlayerWeekStat(models.Model):
    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="weekly_stats"
    )
    week = models.ForeignKey(Week, on_delete=models.CASCADE, related_name="player_stats")

    goals = models.PositiveSmallIntegerField(default=0)
    assists = models.PositiveSmallIntegerField(default=0)
    points = models.PositiveSmallIntegerField(default=0)

    penalty_minutes = models.PositiveSmallIntegerField(default=0)
    powerplay_goals = models.PositiveSmallIntegerField(default=0)
    powerplay_assists = models.PositiveSmallIntegerField(default=0)
    shorthanded_goals = models.PositiveSmallIntegerField(default=0)

    loose_balls = models.PositiveSmallIntegerField(default=0)
    turnovers = models.PositiveSmallIntegerField(default=0)
    caused_turnovers = models.PositiveSmallIntegerField(default=0)

    blocked_shots = models.PositiveSmallIntegerField(default=0)
    shots_on_goal = models.PositiveSmallIntegerField(default=0)

    faceoff_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0.00 to 100.00",
    )

    source_file = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "week"], name="uniq_player_week_stat"
            ),
        ]
        indexes = [
            models.Index(fields=["week", "player"]),
            models.Index(fields=["player", "week"]),
        ]
        ordering = ["week__season", "week__week_number", "player__last_name"]

    def __str__(self) -> str:
        return f"{self.player} - {self.week}"


class ImportRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"

    uploaded_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_runs",
    )

    uploaded_file = models.FileField(upload_to="imports/")
    original_filename = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    players_created = models.PositiveIntegerField(default=0)
    players_updated = models.PositiveIntegerField(default=0)
    weeks_created = models.PositiveIntegerField(default=0)
    weeks_updated = models.PositiveIntegerField(default=0)
    stats_created = models.PositiveIntegerField(default=0)
    stats_updated = models.PositiveIntegerField(default=0)

    log = models.TextField(blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ImportRun {self.id} - {self.status} - {self.original_filename or self.uploaded_file.name}"


class FantasyTeamOwner(models.Model):
    """Links Django User accounts to fantasy Teams (for chat & ownership)"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fantasy_owner",
    )
    team = models.OneToOneField(
        Team,
        on_delete=models.CASCADE,
        related_name="owner",
        help_text="The fantasy team this user owns"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["team__name"]

    def __str__(self) -> str:
        return f"{self.user.username} owns {self.team.name}"


class ChatMessage(models.Model):
    """League chat messages and system notifications"""
    class MessageType(models.TextChoices):
        CHAT = "CHAT", "Chat Message"
        ADD = "ADD", "Player Added"
        DROP = "DROP", "Player Dropped"
        TRADE = "TRADE", "Trade"
        SYSTEM = "SYSTEM", "System Notification"

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages",
        help_text="User who sent the message (null for system messages)"
    )
    message_type = models.CharField(
        max_length=10,
        choices=MessageType.choices,
        default=MessageType.CHAT
    )
    message = models.TextField()
    
    # For transaction notifications
    player = models.ForeignKey(
        Player,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Player involved in add/drop/trade"
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        help_text="Team involved in transaction"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["message_type"]),
        ]

    def __str__(self) -> str:
        sender_name = self.sender.username if self.sender else "System"
        return f"[{self.message_type}] {sender_name}: {self.message[:50]}"
