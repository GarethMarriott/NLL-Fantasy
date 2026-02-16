# Database Query Optimization Analysis

## Phase 2: Database Query Performance Issues

Identified critical N+1 query patterns and inefficient database access that significantly impact page load times.

---

## 1. **CRITICAL: standings() View - Nested Loop Inefficiency** 

**File:** [web/views.py](web/views.py#L3073)  
**Severity:** 🔴 HIGH - Page load bottleneck  
**Current Impact:** 100-180+ loop iterations with Python filtering  

### The Problem

```python
# Line 3131: Prefetch data ONE time (good!)
all_rosters = list(
    Roster.objects.filter(team__in=teams, league=league, player__active=True)
    .select_related("player", "team")
    .prefetch_related("player__game_stats__game__week")
)

# Lines 3159-3196: Called 100+ times (teams × weeks)
def team_week_total(team_id, week_number):
    # PROBLEM: Loop through ALL rosters, filter in Python
    for roster_entry in all_rosters:  # Could be 140 items total
        if roster_entry.team_id == team_id:  # Python filtering - inefficient!
            active_players.append(roster_entry.player)
    
    # Then iterate players and access stats
    for p in active_players:
        stat = next((s for s in p.game_stats.all() if ...), None)
```

### Performance Impact Example
- 10 teams in league
- 18 completed weeks
- 360 games (18 weeks × 10 teams = 180 games per round-robin minimum)
- 140 roster entries total
- **Function called:** 180-360+ times per standings page load
- **Each call:** Loops through 140 items to find 12-14 for this team
- **Wasted iterations:** 140 × 180 = 25,200 loop iterations per page load!

### Recommended Solution

```python
# Group rosters by team_id ONE TIME
rosters_by_team = defaultdict(list)
for roster_entry in all_rosters:
    rosters_by_team[roster_entry.team_id].append(roster_entry)

def team_week_total(team_id, week_number):
    # Now access only relevant rosters
    team_rosters = rosters_by_team[team_id]  # ~12-14 items instead of 140
    
    active_players = []
    for roster_entry in team_rosters:  # Only team's rosters
        if week_added <= week_number < week_dropped:
            active_players.append(roster_entry.player)
    
    for p in active_players:
        stat = next((s for s in p.game_stats.all() if ...), None)
        # Game stats already prefetched from line 3131!
```

### Optimization Gain
- **Before:** 25,200+ loop iterations + Python filtering
- **After:** Loop only relevant roster entries (12-14 instead of 140)
- **Expected:** 2-4x faster standings page load

---

## 2. **HIGH: team_detail() View - Multiple Stat Lookups**

**File:** [web/views.py](web/views.py#L318)  
**Severity:** 🟠 HIGH - Called per page + per player  
**Current Impact:** Multiple `.game_stats.all()` calls in loops  

### The Problem

```python
# Line 372: Good prefetch setup
roster = team.roster_entries.select_related('player').prefetch_related(...)

# Lines 457-460: But then loops through stats without efficient filtering
for p in active_players:
    # Loop through all game_stats looking for matching week
    for stat in p.game_stats.all():
        if stat.game.week_id == week_obj.id:
            latest_stat = stat
```

### Recommended Solution

```python
# Create a stat index by player and week
stat_by_player_week = {}
for stat in all_stats:  # Get all stats once
    key = (stat.player_id, stat.game.week_id)
    stat_by_player_week[key] = stat

# Then lookup is O(1) instead of loop
stat = stat_by_player_week.get((player.id, week_obj.id))
```

---

## 3. **HIGH: matchups() View - Similar Pattern to standings()**

**File:** [web/views.py](web/views.py#L2844)  
**Severity:** 🟠 HIGH  
**Current Impact:** Roster filtering in Python loops  

### The Problem

Lines 2924-2980: Same pattern as standings - loops through all rosters checking `team.id`:

```python
for team in teams:
    for player in team_rosters:  # Loops all rosters
        if player.team_id == team.id:  # Python filtering
            # Process player
```

### Solution
Apply same roster grouping strategy as standings optimization.

---

## 4. **CRITICAL: create_rookie_draft() & _calculate_draft_order_from_standings() - N+1 in Nested Loops**

**File:** [web/tasks.py](web/tasks.py#L498)  
**Severity:** 🔴 HIGH - Executes offline but slow  
**Current Impact:** Quadratic complexity (teams × rosters)  

### The Problem

```python
# Line 507: Prefetch rosters with stats
all_rosters = list(
    Roster.objects.filter(team__in=teams, league=league, player__active=True)
    .select_related("player", "team")
    .prefetch_related("player__game_stats__game__week")
)

# Lines 953-980: Loop through teams, then loop through ALL rosters
for week in completed_weeks:
    for i in range(0, len(teams), 2):
        team1 = teams[i]
        team2 = teams[i + 1]
        
        team1_total = 0.0
        for roster_entry in all_rosters:  # Loops all rosters
            if roster_entry.team_id == team1.id:  # Python filter
                # Calculate points
```

### Optimization Gain
- **Before:** O(n²) - loops teams & rosters
- **After:** O(n) with grouping
- **Example:** 10 teams × 140 rosters = 1,400 iterations → 140 iterations

---

## 5. **MODERATE: players() View - Multiple Stat Access**

**File:** [web/views.py](web/views.py#L2048)  
**Severity:** 🟡 MODERATE  
**Current:** Line 2074 has good prefetch: `prefetch_related("game_stats__game__week")`  

### Status
✅ Already optimized - continue as is.

---

## 6. **MODERATE: trade_center() View - Player Schedule Queries**

**File:** [web/views.py](web/views.py#L1609)  
**Severity:** 🟡 MODERATE  

### The Problem

```python
# Lines 1613-1614: Called for EACH player in roster
for roster_entry in user_roster:
    roster_entry.player.upcoming_schedule = get_player_upcoming_schedule(...)
    # Gets games for this player (queries database)

for other_team in other_teams:
    for roster_entry in other_team.roster_entries.all():
        roster_entry.player.upcoming_schedule = get_player_upcoming_schedule(...)
        # Queries database AGAIN for each player!
```

### Solution
- Batch query all games once
- Build a schedule map by player_id
- Assign from map instead of per-player queries

---

## Optimization Priority & Effort

| Priority | Issue | File | Lines | Est. Effort | Gain |
|----------|-------|------|-------|-------------|------|
| 🔴 P1 | standings() grouping | views.py | 3131-3196 | 30 min | 2-4x faster |
| 🔴 P2 | team_detail() stat indexing | views.py | 318-460 | 20 min | 1.5-2x faster |
| 🔴 P3 | matchups() grouping | views.py | 2924-2980 | 20 min | 2-3x faster |
| 🟠 P4 | draft tasks grouping | tasks.py | 507-980 | 25 min | 5-10x faster drafts |
| 🟡 P5 | trade_center schedules | views.py | 1609-1614 | 15 min | 1.5x faster |

---

## Implementation Roadmap

### Phase 2a: standings() Optimization (FIRST - biggest impact)
1. Create `rosters_by_team` dictionary grouping
2. Update `team_week_total()` to use grouped data
3. Test standings page load
4. Expected gain: Fastest noticeable improvement

### Phase 2b: team_detail() Optimization  
1. Create stat index by player_week
2. Replace loop lookups with dictionary access
3. Test player detail pages
4. Expected gain: Faster page loads with many players

### Phase 2c: matchups() Optimization
1. Apply roster grouping from standings
2. Simplify roster filtering
3. Test matchups page
4. Expected gain: Faster scheduling calculations

### Phase 2d: Celery Tasks (draft_order, create_rookie_draft)
1. Apply grouping strategy
2. Test to ensure rankings calculate correctly
3. Expected gain: 5-10x faster draft creation

### Phase 2e: trade_center() Batch Queries
1. Fetch all schedules once
2. Map to players
3. Test trade page
4. Expected gain: Slight improvement only

---

## Database Query Optimization Best Practices Applied

✅ Use `select_related()` for foreign keys (already doing)  
✅ Use `prefetch_related()` for reverse relations (already doing)  
⚠️ Group prefetched data by lookup key (NOT doing - need to add)  
⚠️ Avoid filtering prefetched querysets in Python loops (currently doing - need to fix)  
⚠️ Cache lookups in dictionaries for repeated access (NOT doing - need to add)  

---

## Success Criteria

- [ ] standings() page loads <500ms (from current ~2-3s)
- [ ] team_detail() renders <300ms (from current ~500-800ms)  
- [ ] matchups() page <1s (from current ~2s)
- [ ] Draft creation <10s (from current 30-45s)

---

## Files to Modify

1. **web/views.py** (3 optimization points)
   - `standings()` function
   - `team_detail()` function  
   - `matchups()` function

2. **web/tasks.py** (2 optimization points)
   - `create_rookie_draft()` function
   - `_calculate_draft_order_from_standings()` function

---

## Next Steps

Ready to implement Phase 2a (standings optimization) which should provide the most noticeable improvement for end-users visiting the standings page.
