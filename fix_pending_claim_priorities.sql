-- Update pending waiver claim priorities to match current team priorities
UPDATE web_waiverclaim wc
SET priority = t.waiver_priority
FROM web_team t
WHERE wc.team_id = t.id
  AND wc.status = 'PENDING';

-- Show the updated claims
SELECT wc.id, t.name, wc.priority, t.waiver_priority, wc.status, p.first_name, p.last_name
FROM web_waiverclaim wc
JOIN web_team t ON wc.team_id = t.id
JOIN web_player p ON wc.player_to_add_id = p.id
WHERE wc.status = 'PENDING'
ORDER BY wc.created_at DESC;
