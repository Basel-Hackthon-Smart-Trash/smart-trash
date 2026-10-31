"""All thresholds in one place, so the team can tune them without touching the logic."""

# Sensor design (option 1): measure every 30 min, send a batch every 3 h,
# send immediately at ALARM_FILL, and send one fresh batch before planning
READING_INTERVAL_MIN = 30          # sensor MEASURES every 30 minutes
SEND_INTERVAL_H = 3                # sensor SENDS a batch of readings every 3 hours
ALARM_FILL = 90                    # sensor sends immediately when this full
FRESH_SEND_TIME = "05:30"          # extra send before the morning planning
PLANNING_TIME = "06:00"            # run_daily runs after the fresh data arrived

# Emptying detection: a drop this big means the crew emptied the bin
EMPTY_DROP_POINTS = 30

# Status rules (match the dashboard colours)
# Rule "E" from policy_test: almost no overflows, still less driving than the old schedule
RED_FILL = 90                      # empty today if at least this full ...
RED_FULL_WITHIN_H = 24             # ... or full before tomorrow's tour (clock hours)
ORANGE_FILL = 70                   # orange = 70-89 %, also emptied today
ORANGE_FULL_WITHIN_H = None        # no time rule for orange
TAKE_ORANGE = True                 # routing takes red AND orange bins

# Routing: truck limits (ALL ASSUMPTIONS, check with the Werkhof)
BIN_VOLUME_L = 110                 # volume of a public bin if unknown (litres)
TRUCK_CAPACITY_L = 6000            # loose waste a truck can carry per tour (litres, after compaction)
SHIFT_HOURS = 6.5                  # working time per tour (8 h shift minus breaks and depot time)
AVG_SPEED_KMH = 18                 # average city driving speed incl. traffic lights
SERVICE_MIN_PER_BIN = 2.0          # stop, empty, new bag, go
WALK_SPEED_KMH = 4.0               # for bins far from a drivable street (there and back)
MAX_TRUCKS = 8                     # hard limit, warn if more are needed

# Team routing package (code/routing): one OR-Tools solve per truck tour
DEPOT_NODE_ID = "werkhof-bruessel-strasse"   # TO DISCUSS: routing team modelled "kva-basel" (KVA, Hagenaustrasse 40)
ROUTING_TIME_LIMIT_S = 3.0                  # OR-Tools search time per tour
TIMEZONE = "Europe/Zurich"
TRUCK_CAPACITY = 40                # (old rule of thumb, only used by zone_test/policy_test)

# Fault rules
STUCK_HOURS = 8                    # no change for this long during the day = stuck
STUCK_MAX_RANGE = 1.0              # "no change" = values move less than 1 point
FULL_IS_NOT_STUCK = 95             # a bin at 95-100 % may sit still legitimately (bug #2!)
JUMP_POINTS = 40                   # rise of 40+ points in one reading = suspicious jump
JUMP_FREEZE_READINGS = 6           # ... followed by 3 h of no change = jump-and-freeze
PARTIAL_DROP_MIN = 8               # drops between 8 and 30 points: bins don't empty halfway
NO_DATA_HOURS = 7                  # two missed 3-hour batches (+ margin) = sensor offline
LOW_BATTERY = 15                   # warning, not a fault
DAY_START_H, DAY_END_H = 7, 21     # people use bins mainly in these hours
