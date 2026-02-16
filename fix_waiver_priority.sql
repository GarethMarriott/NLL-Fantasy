-- Update waiver priorities for all teams, ordering by league and team ID
WITH RankedTeams AS (
  SELECT id, league_id, ROW_NUMBER() OVER (PARTITION BY league_id ORDER BY id) as new_priority
  FROM web_team
)
UPDATE web_team SET waiver_priority = RankedTeams.new_priority
FROM RankedTeams
WHERE web_team.id = RankedTeams.id;

-- Verify the changes
SELECT l.name, t.name, t.waiver_priority 
FROM web_team t
JOIN web_league l ON t.league_id = l.id
ORDER BY l.name, t.waiver_priority;
