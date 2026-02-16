-- Update all week unlock times to be Tuesday at 5pm UTC (9am PT)
-- instead of Monday at 5pm UTC
-- 
-- For each week, we find the Friday lock time, then set unlock to Tuesday of that week at 5pm UTC

UPDATE web_week SET roster_unlock_time = 
  -- Set to 3 days before Friday lock time (Tuesday) at 5pm UTC
  (roster_lock_time AT TIME ZONE 'UTC')::date - interval '3 days' + interval '17 hours'
WHERE roster_unlock_time IS NOT NULL;

-- Verify the changes
SELECT week_number, season, roster_unlock_time, roster_lock_time 
FROM web_week 
WHERE roster_unlock_time IS NOT NULL
ORDER BY season, week_number;
