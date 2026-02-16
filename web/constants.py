"""
NLL Fantasy - Constants and Mappings

This module contains shared constants used across views to avoid duplication.
"""

# NLL Team Name to ID Mapping
# Maps official NLL team names to their game database IDs
TEAM_NAME_TO_ID = {
    "Vancouver Warriors": "867",
    "San Diego Seals": "868",
    "Colorado Mammoth": "870",
    "Calgary Roughnecks": "874",
    "Saskatchewan Rush": "879",
    "Philadelphia Wings": "880",
    "Buffalo Bandits": "888",
    "Georgia Swarm": "890",
    "Toronto Rock": "896",
    "Halifax Thunderbirds": "912",
    "Panther City Lacrosse Club": "913",
    "Albany FireWolves": "914",
    "Las Vegas Desert Dogs": "915",
    "New York Riptide": "911",
    "Ottawa Black Bears": "917",
    "Oshawa FireWolves": "918",
    "Rochester Knighthawks": "910",
}

# NLL Team ID to Name Mapping (reverse of above)
TEAM_ID_TO_NAME = {v: k for k, v in TEAM_NAME_TO_ID.items()}

# Extended NLL team mapping with historical teams (for schedules)
EXTENDED_TEAM_ID_TO_NAME = {
    867: "Vancouver Warriors",
    868: "San Diego Seals",
    869: "Vancouver Ravens",
    870: "Colorado Mammoth",
    871: "Arizona Sting",
    872: "Anaheim Storm",
    873: "Ottawa Rebel",
    874: "Calgary Roughnecks",
    875: "Montreal Express",
    876: "New Jersey Storm",
    877: "San Jose Stealth",
    878: "Minnesota Swarm",
    879: "Saskatchewan Rush",
    880: "Philadelphia Wings",
    881: "New Jersey Saints",
    882: "Baltimore Thunder",
    883: "Washington Wave",
    884: "Detroit Turbos",
    885: "Philadelphia Wings[1]",
    886: "New England Blazers",
    887: "New York Saints",
    888: "Buffalo Bandits",
    889: "Pittsburgh Bulls",
    890: "Georgia Swarm",
    891: "New England Black Wolves",
    892: "Rochester Knighthawks[1]",
    893: "Boston Blazers",
    894: "Ontario Raiders",
    895: "Charlotte Cobras",
    896: "Toronto Rock",
    897: "Syracuse Smash",
    898: "Pittsburgh Crossefire",
    899: "Albany Attack",
    900: "Columbus Landsharks",
    901: "Washington Power",
    902: "Portland Lumberjax",
    903: "Edmonton Rush",
    904: "Vancouver Stealth",
    905: "Boston Blazers[1]",
    906: "Washington Stealth",
    907: "Orlando Titans",
    908: "New York Titans",
    909: "Chicago Shamrox",
    910: "Rochester Knighthawks",
    911: "New York Riptide",
    912: "Halifax Thunderbirds",
    913: "Panther City Lacrosse Club",
    914: "Albany FireWolves",
    915: "Las Vegas Desert Dogs",
    917: "Ottawa Black Bears",
    918: "Oshawa FireWolves",
}
