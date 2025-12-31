"""Merge migration for conflicting 0010 migrations.

This migration resolves the multiple-leaf conflict by depending on both
conflicting 0010 migrations. It has no operations.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0010_ensure_player_team_column_sql"),
        ("web", "0010_remove_player_team_importrun_team"),
    ]

    operations = []
