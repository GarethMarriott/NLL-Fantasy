"""Ensure `web_player.team_id` column and FK exist (idempotent SQL).

This migration runs raw SQL to add the `team_id` column and a foreign-key
constraint if they do not already exist. It is defensive to repair a
mismatched DB state caused by earlier conflicting migrations.
"""
from django.db import migrations


SQL_UP = """
ALTER TABLE web_player ADD COLUMN IF NOT EXISTS team_id bigint;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'web_player_team_id_fkey'
    ) THEN
        ALTER TABLE web_player
        ADD CONSTRAINT web_player_team_id_fkey
        FOREIGN KEY (team_id) REFERENCES web_team (id) ON DELETE SET NULL;
    END IF;
END
$$;
"""

SQL_DOWN = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'web_player_team_id_fkey'
    ) THEN
        ALTER TABLE web_player DROP CONSTRAINT web_player_team_id_fkey;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='web_player' AND column_name='team_id'
    ) THEN
        ALTER TABLE web_player DROP COLUMN team_id;
    END IF;
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0009_fix_player_team_and_remove_importrun_team"),
    ]

    operations = [
        migrations.RunSQL(SQL_UP, SQL_DOWN),
    ]
