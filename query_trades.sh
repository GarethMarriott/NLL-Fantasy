#!/bin/bash
cd /opt/shamrock-fantasy
sqlite3 db.sqlite3 << EOF
SELECT id, status, executed_at, proposing_team_id, receiving_team_id FROM web_trade ORDER BY created_at DESC LIMIT 20;
EOF
