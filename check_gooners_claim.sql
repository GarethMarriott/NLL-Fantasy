SELECT wc.id, t.name, wc.priority, wc.status, wc.created_at, p.first_name, p.last_name, p.number
FROM web_waiverclaim wc
JOIN web_team t ON wc.team_id = t.id
JOIN web_player p ON wc.player_to_add_id = p.id
WHERE t.name LIKE '%Goon%'
ORDER BY wc.created_at DESC;
