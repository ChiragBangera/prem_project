from __future__ import annotations

import asyncio
import time
from typing import Any

from .analytics import career as career_engine
from .analytics import player as player_engine
from .analytics import team as team_engine
from .analytics import league as league_engine
from .analytics import match as match_engine
from .analytics._shared import as_list_matches
from .ml.engine import build_match_rows
from .stat_data import UnderstatData
from .utils.utils import get_current_season


LEAGUES = ("EPL", "La_liga", "Serie_A", "Bundesliga", "Ligue_1")
DEFAULT_CAREER_SEASONS = 6
DEFAULT_SEASON = get_current_season()

# forecast cache: (league, season) -> (timestamp, {match_id_str: forecast_dict})
_forecast_cache: dict[tuple[str, int], tuple[float, dict[str, dict]]] = {}
_FORECAST_TTL = 300  # 5 minutes


def _valid_date_range(start_date: str | None, end_date: str | None) -> tuple[str | None, str | None]:
    start = start_date.strip() if start_date and start_date.strip() else None
    end = end_date.strip() if end_date and end_date.strip() else None
    if start and end and start > end:
        raise ValueError(f"start_date ({start}) must not be after end_date ({end}).")
    return start, end


def parse_seasons(value) -> list[int] | None:
    """Accept an int, a list of ints, or a comma-separated string like "2024,2025"."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        seasons = sorted({int(s) for s in value if s is not None})
        return seasons or None
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        if not parts:
            return None
        try:
            seasons = sorted({int(part) for part in parts})
        except ValueError as exc:
            raise ValueError(f"Invalid season list '{value}': use comma-separated years, e.g. '2024,2025'.") from exc
        return seasons or None
    return [int(value)]


def _normalize_name(name) -> str:
    """Case- and accent-insensitive name key ('João Pedro' == 'joao pedro')."""
    import unicodedata
    value = unicodedata.normalize("NFD", (name or "").lower())
    return "".join(char for char in value if unicodedata.category(char) != "Mn").strip()


def _find_player_in_league(name: str, players: list[dict]):
    target = _normalize_name(name)
    for player in players:
        if _normalize_name(player.get("player_name")) == target:
            return player
    return None


class AnalyticsService:
    """Fetches the right Understat data and runs the pure analytics engines over it."""

    def __init__(self, client: UnderstatData | None = None, enrichment=None):
        self.client = client or UnderstatData()
        self.enrichment = enrichment

    async def analyze_player(
        self,
        player_id: int | None = None,
        player_name: str | None = None,
        league_name: str = "EPL",
        season: int = DEFAULT_SEASON,
        start_date: str | None = None,
        end_date: str | None = None,
        seasons: list[int] | str | None = None,
    ) -> dict:
        if player_id is None and player_name is None:
            raise ValueError("Either player_id or player_name is required.")

        start_date, end_date = _valid_date_range(start_date, end_date)
        target_seasons = parse_seasons(seasons) or [season]

        import asyncio

        season_stats = await asyncio.gather(
            *(
                self.client.get_league_player_stats(
                    league_name, current_season, start_date=start_date, end_date=end_date
                )
                for current_season in target_seasons
            ),
            return_exceptions=True,
        )
        valid = [rows for rows in season_stats if isinstance(rows, list)]
        if not valid:
            raise ValueError(f"No league player stats could be loaded for {league_name} {target_seasons}.")

        merged_by_id = _merge_league_players(valid)
        if player_id is None:
            # League-first resolution with accent folding: find the name in the
            # season tables before falling back to the global search (the
            # search can return a namesake in another league, e.g. João Pedro).
            by_name = _find_player_in_league(player_name, list(merged_by_id.values()))
            if by_name is not None:
                player_id = int(by_name["id"])
            else:
                matches = await self.client.search_players(player_name)
                if not matches:
                    raise ValueError(f"Player '{player_name}' was not found via Understat search.")
                player_id = int(matches[0]["id"])

        target = merged_by_id.get(player_id)
        if target is None:
            # Fallback: discover the player's most recent active season in this league
            if hasattr(self.client, "get_player_data"):
                try:
                    p_data = await self.client.get_player_data(player_id)
                    groups = p_data.get("groups", {}) if isinstance(p_data, dict) else {}
                    seasons_list = groups.get("season", [])
                    if isinstance(seasons_list, list) and seasons_list:
                        for s_entry in seasons_list:
                            s_yr = int(s_entry.get("season", 0))
                            if s_yr and s_yr not in target_seasons:
                                fallback_stats = await self.client.get_league_player_stats(
                                    league_name, s_yr, start_date=start_date, end_date=end_date
                                )
                                if isinstance(fallback_stats, list) and fallback_stats:
                                    fallback_merged = _merge_league_players([fallback_stats])
                                    if player_id in fallback_merged:
                                        merged_by_id = fallback_merged
                                        target = merged_by_id[player_id]
                                        target_seasons = [s_yr]
                                        break
                except Exception:
                    pass

        if target is None:
            window = _window_label(start_date, end_date)
            raise ValueError(
                f"Player id {player_id} is not in {league_name} {target_seasons}{window} per the league player stats tables."
            )

        all_merged = list(merged_by_id.values())
        teammates = [
            p for p in all_merged
            if p.get("team_title") == target.get("team_title") and int(p.get("id", 0)) != player_id
        ]

        shots = None
        try:
            raw_shots = await self.client.get_player_shots(player_id)
            shots = _filter_shots_to_seasons(raw_shots, target_seasons, start_date, end_date)
        except Exception:
            shots = None

        report = player_engine.player_report(target, all_merged, teammates, shots=shots)

        try:
            birthdates = await self._birthdate_map([target.get("player_name")], [target])
            report["player"]["age"] = _age(birthdates.get(target.get("player_name")))
            report["player"]["date_of_birth"] = birthdates.get(target.get("player_name"))
            similar_names = [m.get("player_name") for m in report.get("similar_players", {}).get("matches", [])]
            if similar_names:
                similar_birthdates = await self._birthdate_map(similar_names, [
                    {"player_name": name} for name in similar_names
                ])
                for match in report["similar_players"]["matches"]:
                    match["age"] = _age(similar_birthdates.get(match.get("player_name")))
        except Exception:
            pass

        favorite = await self._favorite_position(player_id)
        if favorite:
            from .analytics.percentiles import group_from_favorite
            report["player"]["favorite_position"] = favorite
            report["player"]["position_group"] = group_from_favorite(favorite)

        if shots:
            report["shots"] = [
                {
                    "minute": s.get("minute"),
                    "xG": round(float(s.get("xG") or 0), 4),
                    "result": s.get("result"),
                    "situation": s.get("situation"),
                    "shotType": s.get("shotType"),
                    "lastAction": s.get("lastAction"),
                    "player": s.get("player") or target.get("player_name"),
                    "X": float(s.get("X") or 0),
                    "Y": float(s.get("Y") or 0),
                    "date": (s.get("date") or "")[:10],
                    "h_a": s.get("h_a"),
                    "season": s.get("season"),
                    "player_assisted": s.get("player_assisted"),
                }
                for s in shots
            ]

        # shot_profile_detail from groups already fetched via get_player_data
        shot_profile_detail = None
        try:
            if hasattr(self.client, "get_player_data"):
                try:
                    p_data = await self.client.get_player_data(player_id)
                    groups = p_data.get("groups") if isinstance(p_data, dict) else None
                except Exception:
                    groups = None
                if groups:
                    requested_season = target_seasons[-1] if target_seasons else season
                    profile = career_engine.shot_profile_for_season(groups, requested_season)
                    profile_season: int | None = requested_season if profile is not None else None
                    if profile is None and len(target_seasons) > 1:
                        # try other requested seasons in reverse
                        for s_yr in reversed(target_seasons[:-1]):
                            p = career_engine.shot_profile_for_season(groups, s_yr)
                            if p is not None:
                                profile = p
                                profile_season = s_yr
                                break
                    # Fallback to any available season in groups if still missing (e.g., request 2025 but only 2024 exists)
                    if profile is None:
                        available: set[int] = set()
                        for key in ("situation", "shotZones", "shotTypes", "position"):
                            val = groups.get(key)
                            if isinstance(val, dict):
                                for k in val.keys():
                                    try:
                                        available.add(int(k))
                                    except Exception:
                                        continue
                        season_list = groups.get("season")
                        if isinstance(season_list, list):
                            for entry in season_list:
                                try:
                                    if isinstance(entry, dict) and "season" in entry:
                                        available.add(int(entry.get("season")))
                                    else:
                                        available.add(int(entry))
                                except Exception:
                                    continue
                        # prefer seasons closest to requested (descending, fallback to previous year first)
                        for yr in sorted(available, reverse=True):
                            if yr == requested_season:
                                continue
                            p = career_engine.shot_profile_for_season(groups, yr)
                            if p is not None:
                                profile = p
                                profile_season = yr
                                break
                    if profile is not None:
                        situations = profile["shot_profile"]["situations"] or []
                        zones = profile["shot_profile"]["zones"] or []
                        types = profile["shot_profile"]["types"] or []
                        role_split = profile.get("role_split")
                        for r in situations:
                            r["_source"] = "groups.situation"
                        for r in zones:
                            r["_source"] = "groups.shotZones"
                        for r in types:
                            r["_source"] = "groups.shotTypes"
                        if role_split:
                            for r in role_split:
                                r["_source"] = "groups.position"
                        is_fallback = profile_season != requested_season
                        if is_fallback:
                            honest_note = f"Requested season {requested_season} unavailable — showing {profile_season} (fallback)."
                            fallback_note = honest_note
                        else:
                            honest_note = "Shot profile for requested season."
                            fallback_note = honest_note
                        shot_profile_detail = {
                            "situations": situations,
                            "zones": zones,
                            "types": types,
                            "role_split": role_split,
                            "profile_season": profile_season,
                            "requested_season": requested_season,
                            "fallback": is_fallback,
                            "honest_note": honest_note,
                            "fallback_note": fallback_note,
                            "note": honest_note,
                        }
                    else:
                        shot_profile_detail = None
                else:
                    shot_profile_detail = None
        except Exception:
            shot_profile_detail = None
        report["shot_profile_detail"] = shot_profile_detail

        # assisted_network via player_assisted aggregation
        if not shots:
            report["assisted_network"] = None
        else:
            from collections import Counter, defaultdict
            assister_agg: dict[str, dict] = {}
            assisted_agg: dict[str, dict] = {}
            for s in shots:
                assister = s.get("player_assisted")
                if assister and str(assister).strip() and str(assister).strip().lower() not in ("none", "null", ""):
                    key = str(assister).strip()
                    if key not in assister_agg:
                        assister_agg[key] = {"assister": key, "count": 0, "assists_xG": 0.0}
                    assister_agg[key]["count"] += 1
                    assister_agg[key]["assists_xG"] += float(s.get("xG") or 0)
                # top_assisted: player assisted others - not derivable from own shots; leave empty
            top_assisters = sorted(assister_agg.values(), key=lambda x: (-x["count"], -x["assists_xG"]))[:5]
            for entry in top_assisters:
                entry["assists_xG"] = round(entry["assists_xG"], 2)
            top_assisted = sorted(assisted_agg.values(), key=lambda x: (-x["count"], -x.get("xG", 0)))[:5]
            report["assisted_network"] = {
                "top_assisters": top_assisters,
                "top_assisted": top_assisted,
                "honest_note": "Aggregated from shots.player_assisted (Understat shot assists, not Opta key passes).",
            }

        # enrichment via provider (noop default)
        try:
            from dataclasses import asdict
            from .analytics.enrichment import ExternalEnrichment, NoopEnrichmentProvider

            provider = self.enrichment if self.enrichment is not None else NoopEnrichmentProvider()
            enrichment_obj = await provider.enrich_player(target.get("player_name"), target.get("team_title"))
            if hasattr(enrichment_obj, "__dataclass_fields__"):
                enrichment_dict = asdict(enrichment_obj)
            elif isinstance(enrichment_obj, dict):
                enrichment_dict = dict(enrichment_obj)
            else:
                enrichment_dict = {
                    "source": getattr(enrichment_obj, "source", "none"),
                    "fetched_at": getattr(enrichment_obj, "fetched_at", None),
                }
            report["enrichment"] = enrichment_dict
        except Exception:
            report["enrichment"] = {
                "source": "none",
                "market_value_eur": None,
                "contract_end": None,
                "foot": None,
                "height_cm": None,
                "sofascore_rating": None,
                "whoscored_rating": None,
                "strengths": [],
                "weaknesses": [],
                "honest_note": "Enrichment not configured (Understat-only in this deploy).",
                "fetched_at": None,
            }

        report["date_window"] = {"start_date": start_date, "end_date": end_date}
        report["seasons"] = target_seasons
        return report

    async def player_career(
        self,
        player_name: str | None = None,
        player_id: int | None = None,
        league_name: str = "EPL",
        seasons: list[int] | None = None,
        season_end: int | None = None,
    ) -> dict:
        if player_id is None and player_name is None:
            raise ValueError("Either player_id or player_name is required.")

        if seasons:
            target_seasons = sorted(int(s) for s in seasons)
        else:
            end = season_end or DEFAULT_SEASON
            target_seasons = list(range(end - DEFAULT_CAREER_SEASONS + 1, end + 1))

        import asyncio

        async def fetch_season(season: int):
            players = await self.client.get_league_player_stats(league_name, season)
            return {
                "season": season,
                "player": next((p for p in players if int(p.get("id", 0)) == player_id), None),
            }

        if player_id is None:
            # league-first resolution (accent-folded) across the career window
            season_rows_all = await asyncio.gather(
                *(self.client.get_league_player_stats(league_name, s) for s in target_seasons),
                return_exceptions=True,
            )
            by_name = None
            for rows in reversed(season_rows_all):
                if not isinstance(rows, list):
                    continue
                by_name = _find_player_in_league(player_name, rows)
                if by_name is not None:
                    break
            if by_name is not None:
                player_id = int(by_name["id"])
                player_name = by_name.get("player_name") or player_name
            else:
                matches = await self.client.search_players(player_name)
                if not matches:
                    raise ValueError(f"Player '{player_name}' was not found via Understat search.")
                resolved = matches[0]
                player_id = int(resolved["id"])
                player_name = resolved.get("player") or resolved.get("player_name") or player_name
        else:
            player_name = player_name or f"player {player_id}"

        season_rows = await asyncio.gather(*(fetch_season(s) for s in target_seasons))
        groups = None
        try:
            player_data = await self.client.get_player_data(player_id)
            groups = player_data.get("groups")
        except Exception:
            groups = None
        return career_engine.career_trajectory(season_rows, player_name, league_name, player_groups=groups)

    async def team_timeline(
        self,
        team_name: str,
        league_name: str = "EPL",
        seasons: list[int] | None = None,
        season_end: int | None = None,
    ) -> dict:
        from .analytics import team_timeline as timeline_engine

        if seasons:
            target_seasons = sorted(int(s) for s in seasons)
        else:
            end = season_end or DEFAULT_SEASON
            target_seasons = [end - 1, end]

        import asyncio

        history_by_season = await asyncio.gather(
            *(self.client.get_team_history(team_name, s, league_name) for s in target_seasons)
        )
        return timeline_engine.team_timeline(
            {season: history for season, history in zip(target_seasons, history_by_season)},
            team_name,
            league_name,
        )

    async def compare_players(
        self,
        player_1: str | None = None,
        player_2: str | None = None,
        players: list[str] | None = None,
        league_name: str = "EPL",
        season: int = DEFAULT_SEASON,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        names = players or [name for name in (player_1, player_2) if name]
        names = [name.strip() for name in names if name and name.strip()]
        if len(names) < 2:
            raise ValueError("At least two players are required.")
        if len(names) > 12:
            raise ValueError("Compare at most 12 players at once.")
        league_players = await self.client.get_league_player_stats(
            league_name, season, start_date=start_date, end_date=end_date
        )
        resolved = await asyncio.gather(
            *(self._resolve_player(name, league_players, league_name, season) for name in names),
            return_exceptions=True,
        )
        pairs = []
        for name, player in zip(names, resolved):
            if isinstance(player, BaseException):
                raise ValueError(str(player))
            pairs.append((name, player))

        shots_by_name: dict[str, list] = {}
        if len(pairs) <= 6 and hasattr(self.client, "get_player_shots"):
            shots_results = await asyncio.gather(
                *(self.client.get_player_shots(int(player.get("id", 0))) for _, player in pairs),
                return_exceptions=True,
            )
            for (name, player), result in zip(pairs, shots_results):
                if isinstance(result, BaseException):
                    continue
                rows = list(result.values()) if isinstance(result, dict) else list(result or [])
                shots_by_name[name] = [row for row in rows if str(row.get("season")) == str(season)]

        reports = {
            name: player_engine.player_report(player, league_players, shots=shots_by_name.get(name))
            for name, player in pairs
        }
        try:
            birthdates = await self._birthdate_map(
                [player.get("player_name") for _, player in pairs], [player for _, player in pairs]
            )
            for name, player in pairs:
                reports[name]["player"]["age"] = _age(birthdates.get(player.get("player_name")))
                reports[name]["player"]["date_of_birth"] = birthdates.get(player.get("player_name"))
        except Exception:
            pass
        from .analytics.percentiles import group_from_favorite
        from .analytics import career as career_engine

        if hasattr(self.client, "get_player_data"):
            profile_results = await asyncio.gather(
                *(self.client.get_player_data(int(player.get("id", 0))) for _, player in pairs),
                return_exceptions=True,
            )
            for (name, player), result in zip(pairs, profile_results):
                if isinstance(result, BaseException):
                    continue
                groups = result.get("groups") if isinstance(result, dict) else None
                profile = career_engine.shot_profile_for_season(groups, season)
                reports[name]["comparison_profile"] = {
                    "shot_profile": profile["shot_profile"] if profile else None,
                    "role_split": profile["role_split"] if profile else None,
                    "minute_buckets": player_engine.shot_minute_buckets(shots_by_name.get(name) or []),
                    "home_away": player_engine.home_away_shot_split(shots_by_name.get(name) or []),
                }

        favorites = await asyncio.gather(
            *(self._favorite_position(int(player.get("id", 0))) for _, player in pairs),
            return_exceptions=True,
        )
        for (name, player), favorite in zip(pairs, favorites):
            if isinstance(favorite, BaseException) or not favorite:
                continue
            reports[name]["player"]["favorite_position"] = favorite
            reports[name]["player"]["position_group"] = group_from_favorite(favorite)
        return {
            "league_name": league_name,
            "season": season,
            "date_window": {"start_date": start_date, "end_date": end_date},
            "pool_size": len(league_players),
            "players": reports,
            "order": names,
            "radar_labels": [entry["label"] for entry in next(iter(reports.values()))["radar"]["profile"]],
            "limitations": next(iter(reports.values()))["limitations"],
        }

    async def compare_teams(
        self,
        team_1: str,
        team_2: str,
        league_name: str = "EPL",
        season: int = DEFAULT_SEASON,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        table = await self.client.get_league_table(
            league_name, season, start_date=start_date, end_date=end_date
        )
        first_row = _find_team_row(table, team_1)
        second_row = _find_team_row(table, team_2)
        if first_row is None or second_row is None:
            raise ValueError(
                f"One of '{team_1}' / '{team_2}' is not in the {league_name} {season} table"
                f"{_window_label(start_date, end_date)}."
            )

        history_1 = _filter_history(
            await self.client.get_team_history(team_1, season, league_name), start_date, end_date
        )
        history_2 = _filter_history(
            await self.client.get_team_history(team_2, season, league_name), start_date, end_date
        )
        meetings = await self._head_to_head(league_name, season, team_1, team_2, start_date, end_date)

        return {
            "league_name": league_name,
            "season": season,
            "date_window": {"start_date": start_date, "end_date": end_date},
            "team_1": {"name": team_1, "report": team_engine.team_report(first_row, team_history=history_1)},
            "team_2": {"name": team_2, "report": team_engine.team_report(second_row, team_history=history_2)},
            "head_to_head": meetings,
        }

    async def _resolve_player(self, name: str, league_players: list[dict], league_name: str, season: int) -> dict:
        by_name = _find_player_in_league(name, league_players)
        if by_name is not None:
            return by_name
        found = await self.client.search_players(name)
        if not found:
            raise ValueError(f"Player '{name}' was not found via Understat search.")
        player_id = int(found[0]["id"])
        target = next((p for p in league_players if int(p.get("id", 0)) == player_id), None)
        if target is None:
            raise ValueError(f"Player '{name}' is not in the {league_name} {season} league stats table.")
        return target

    async def _head_to_head(
        self,
        league_name: str,
        season: int,
        team_1: str,
        team_2: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict]:
        data = await self.client.get_league_data(league_name, season)
        meetings = []
        for item in as_list_matches(data.get("dates", [])):
            home = (item.get("h") or {}).get("title")
            away = (item.get("a") or {}).get("title")
            if {home, away} != {team_1, team_2}:
                continue
            date = (item.get("datetime") or "")[:10]
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue
            goals = item.get("goals") or {}
            xg = item.get("xG") or {}
            meetings.append(
                {
                    "match_id": item.get("id"),
                    "date": date,
                    "home": home,
                    "away": away,
                    "home_goals": _to_int(goals.get("h")),
                    "away_goals": _to_int(goals.get("a")),
                    "home_xg": _to_float(xg.get("h")),
                    "away_xg": _to_float(xg.get("a")),
                    "played": bool(item.get("isResult")),
                }
            )
        return sorted(meetings, key=lambda m: m["date"])

    async def analyze_team(
        self,
        team_name: str,
        league_name: str = "EPL",
        season: int = DEFAULT_SEASON,
        with_shots: bool = False,
        start_date: str | None = None,
        end_date: str | None = None,
        seasons: list[int] | str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        target_seasons = parse_seasons(seasons) or [season]

        import asyncio

        tables = await asyncio.gather(
            *(
                self.client.get_league_table(
                    league_name, current_season, start_date=start_date, end_date=end_date
                )
                for current_season in target_seasons
            ),
            return_exceptions=True,
        )
        team_rows = [_find_team_row(table, team_name) for table in tables if isinstance(table, list)]
        team_rows = [row for row in team_rows if row is not None]
        if not team_rows:
            raise ValueError(
                f"Team '{team_name}' is not in the {league_name} {target_seasons} tables"
                f"{_window_label(start_date, end_date)}."
            )
        team_row = _merge_table_rows(team_rows)

        histories = await asyncio.gather(
            *(self.client.get_team_history(team_name, s, league_name) for s in target_seasons),
            return_exceptions=True,
        )
        histories_by_season: dict[int, list] = {}
        history = []
        for season, batch in zip(target_seasons, histories):
            if isinstance(batch, BaseException):
                continue
            rows = as_list_matches(batch)
            histories_by_season[season] = rows
            history.extend(rows)
        history = _filter_rows_by_date(history, start_date, end_date)

        shots = None
        if with_shots:
            results = await self.client.get_team_results(team_name, target_seasons[-1])
            match_ids = [int(m["id"]) for m in results if m.get("id")]
            all_shots = await asyncio.gather(*(self.client.get_match_shots(mid) for mid in match_ids[:10]))
            shots = []
            for batch in all_shots:
                for side in ("h", "a"):
                    shots.extend(batch.get(side, []))

        league_histories = None
        try:
            league_data = await self.client.get_league_data(league_name, target_seasons[-1])
            league_histories = {
                name: as_list_matches(entry.get("history")) if isinstance(entry, dict) else []
                for name, entry in (league_data.get("teams") or {}).items()
                if isinstance(entry, dict)
            }
        except Exception:
            league_histories = None

        season_trends: dict[int, dict] = {}
        if hasattr(self.client, "get_league_data"):
            league_results = await asyncio.gather(
                *(self.client.get_league_data(league_name, s) for s in target_seasons),
                return_exceptions=True,
            )
            for season, league_data in zip(target_seasons, league_results):
                if isinstance(league_data, BaseException):
                    continue
                per_season_histories = {
                    name: as_list_matches(entry.get("history")) if isinstance(entry, dict) else []
                    for name, entry in (league_data.get("teams") or {}).items()
                    if isinstance(entry, dict)
                }
                if not per_season_histories:
                    continue
                trend = team_engine.position_trend(
                    histories_by_season.get(season, []), per_season_histories
                )
                for matchday in trend["matchdays"]:
                    matchday["season"] = season
                season_trends[season] = trend

        if season_trends:
            concatenated = []
            for season in target_seasons:
                if season in season_trends:
                    concatenated.extend(season_trends[season]["matchdays"])
            position_trend = {
                "matchdays": concatenated,
                "n_teams": max((t["n_teams"] for t in season_trends.values()), default=1),
            }
        else:
            position_trend = team_engine.position_trend(history, league_histories or {})

        report = team_engine.team_report(team_row, team_history=history, team_shots=shots,
                                        league_histories=league_histories)
        report["position_trend"] = position_trend
        report["season_trends"] = {str(s): t for s, t in sorted(season_trends.items())} if season_trends else None
        report["date_window"] = {"start_date": start_date, "end_date": end_date}
        report["seasons"] = target_seasons

        try:
            raw_squad = await self.client.get_team_player_stats(
                team_name, str(target_seasons[-1]), start_date=start_date, end_date=end_date
            )
            report["squad"] = [
                {
                    "player_name": p.get("player_name"),
                    "games": int(float(p.get("games", 0))),
                    "minutes": int(float(p.get("time", 0))),
                    "goals": int(float(p.get("goals", 0))),
                    "xG": round_value(float(p.get("xG", 0))),
                    "npxG": round_value(float(p.get("npxG", 0))),
                    "assists": int(float(p.get("assists", 0))),
                    "xA": round_value(float(p.get("xA", 0))),
                    "shots": int(float(p.get("shots", 0))),
                    "key_passes": int(float(p.get("key_passes", 0))),
                    "yellow_cards": int(float(p.get("yellow_cards", 0))),
                    "red_cards": int(float(p.get("red_cards", 0))),
                    "position": p.get("position"),
                    "team_title": p.get("team_title"),
                    "npg": int(float(p.get("npg", 0))),
                    "xGChain": round_value(float(p.get("xGChain", 0))),
                    "xGBuildup": round_value(float(p.get("xGBuildup", 0))),
                }
                for p in raw_squad if isinstance(p, dict)
            ]
        except Exception:
            report["squad"] = []

        return report

    async def analyze_league(
        self,
        league_name: str = "EPL",
        season: int = DEFAULT_SEASON,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        table = await self.client.get_league_table(
            league_name, season, start_date=start_date, end_date=end_date
        )
        report = league_engine.league_report(table)
        report["date_window"] = {"start_date": start_date, "end_date": end_date}
        return report

    async def match_rounds(self, league_name: str = "EPL", season: int = DEFAULT_SEASON) -> dict:
        """League matches grouped by derived round (home team's nth league match).

        Understat does not label gameweeks, so a match's round is the count of
        league matches the home team had played through that date. In a normal
        season this matches the official gameweek; postponements can shift a
        fixture by a week or two.
        """
        data = await self.client.get_league_data(league_name, season)
        rows = build_match_rows(data.get("dates", []))
        played = sorted((r for r in rows if r["is_result"]), key=lambda r: (r["date"], r["home"]))
        by_round: dict[int, list[dict]] = {}
        team_played: dict[str, int] = {}
        for row in played:
            for team in (row["home"], row["away"]):
                team_played[team] = team_played.get(team, 0) + 1
            round_number = team_played[row["home"]]
            by_round.setdefault(round_number, []).append(row)
        rounds = []
        for round_number in sorted(by_round):
            matches = sorted(by_round[round_number], key=lambda r: r["date"])
            rounds.append(
                {
                    "round": round_number,
                    "matches": [
                        {
                            "match_id": str(row["match_id"]),
                            "id": str(row["match_id"]),
                            "date": row["date"],
                            "home": row["home"],
                            "away": row["away"],
                            "home_goals": row["home_goals"],
                            "away_goals": row["away_goals"],
                            "home_xg": row["home_xg"],
                            "away_xg": row["away_xg"],
                        }
                        for row in matches
                    ],
                }
            )

        # upcoming_by_round: same home nth match grouping for fixtures
        upcoming = sorted((r for r in rows if not r["is_result"]), key=lambda r: (r["date"], r["home"]))
        upcoming_by_round: dict[int, list[dict]] = {}
        # continue counting from played base so round numbers continue
        upcoming_team_played = dict(team_played)
        for row in upcoming:
            for team in (row["home"], row["away"]):
                upcoming_team_played[team] = upcoming_team_played.get(team, 0) + 1
            round_number = upcoming_team_played[row["home"]]
            upcoming_by_round.setdefault(round_number, []).append(row)
        upcoming_rounds = []
        for round_number in sorted(upcoming_by_round):
            matches = sorted(upcoming_by_round[round_number], key=lambda r: r["date"])
            upcoming_rounds.append(
                {
                    "round": round_number,
                    "matches": [
                        {
                            "match_id": str(row["match_id"]),
                            "id": str(row["match_id"]),
                            "date": row["date"],
                            "home": row["home"],
                            "away": row["away"],
                            "home_goals": row["home_goals"],
                            "away_goals": row["away_goals"],
                            "home_xg": row["home_xg"],
                            "away_xg": row["away_xg"],
                            "isResult": False,
                            **(
                                {"forecast": {"w": float(row["forecast"]["w"]), "d": float(row["forecast"]["d"]), "l": float(row["forecast"]["l"]), "source": "understat"}}
                                if row.get("forecast") and isinstance(row["forecast"], dict) and "w" in row["forecast"]
                                else {}
                            ),
                        }
                        for row in matches
                    ],
                }
            )
        # if no upcoming but we still need key, provide empty list with grouping fallback using only upcoming counts
        if not upcoming_rounds and upcoming:
            # fallback grouping when there are no played to anchor
            by_upcoming: dict[int, list[dict]] = {}
            tmp: dict[str, int] = {}
            for row in upcoming:
                for team in (row["home"], row["away"]):
                    tmp[team] = tmp.get(team, 0) + 1
                rn = tmp[row["home"]]
                by_upcoming.setdefault(rn, []).append(row)
            for rn in sorted(by_upcoming):
                matches = sorted(by_upcoming[rn], key=lambda r: r["date"])
                upcoming_rounds.append(
                    {
                        "round": rn,
                        "matches": [
                            {
                                "match_id": str(row["match_id"]),
                                "id": str(row["match_id"]),
                                "date": row["date"],
                                "home": row["home"],
                                "away": row["away"],
                                "home_goals": row["home_goals"],
                                "away_goals": row["away_goals"],
                                "home_xg": row["home_xg"],
                                "away_xg": row["away_xg"],
                                "isResult": False,
                                **(
                                    {"forecast": {"w": float(row["forecast"]["w"]), "d": float(row["forecast"]["d"]), "l": float(row["forecast"]["l"]), "source": "understat"}}
                                    if row.get("forecast") and isinstance(row["forecast"], dict) and "w" in row["forecast"]
                                    else {}
                                ),
                            }
                            for row in matches
                        ],
                    }
                )

        latest = sorted(played, key=lambda r: r["date"], reverse=True)[:18]
        latest_matches = [
            {
                "match_id": str(r["match_id"]),
                "id": str(r["match_id"]),
                "date": r["date"],
                "home": r["home"],
                "away": r["away"],
                "home_goals": r["home_goals"],
                "away_goals": r["away_goals"],
                "home_xg": r["home_xg"],
                "away_xg": r["away_xg"],
            }
            for r in latest
        ]

        return {
            "league_name": league_name,
            "season": season,
            "n_played": len(played),
            "rounds": rounds,
            "upcoming_by_round": upcoming_rounds,
            "latest_matches": latest_matches,
            "note": "Round = the home team's nth league match of the season (Understat has no official gameweek label). Forecast from Understat dates.forecast where available.",
        }

    async def analyze_match(self, match_id: int) -> dict:
        shots = await self.client.get_match_shots(match_id)
        home_shots = shots.get("h", [])
        away_shots = shots.get("a", [])
        meta = {
            "h": (home_shots[0].get("h_team") if home_shots else "Home"),
            "a": (away_shots[0].get("a_team") if away_shots else "Away"),
        }
        report = match_engine.match_report(meta, shots)
        # rosters straight from get_match_data
        rosters = None
        try:
            if hasattr(self.client, "get_match_data"):
                match_data = await self.client.get_match_data(match_id)
                raw_rosters = match_data.get("rosters") if isinstance(match_data, dict) else None
                if isinstance(raw_rosters, dict):
                    def _normalize_side(side_data):
                        if isinstance(side_data, dict):
                            return list(side_data.values())
                        if isinstance(side_data, list):
                            return list(side_data)
                        return []
                    h_list = _normalize_side(raw_rosters.get("h"))
                    a_list = _normalize_side(raw_rosters.get("a"))
                    rosters = {"h": h_list, "a": a_list}
                    if raw_rosters is None:
                        rosters = None
                elif raw_rosters is None:
                    rosters = None
                else:
                    rosters = None
        except Exception:
            rosters = None
        report["rosters"] = rosters
        # forecast lookup via league dates — bounded to max 3 fetches with in-memory cache (5-min TTL)
        forecast = None
        try:
            target_id_str = str(match_id)

            async def _get_forecast_map(league: str, season: int) -> dict[str, dict]:
                key = (league, season)
                now = time.time()
                cached = _forecast_cache.get(key)
                if cached and now - cached[0] < _FORECAST_TTL:
                    return cached[1]
                ld = await self.client.get_league_data(league, season)
                mapping: dict[str, dict] = {}
                for item in ld.get("dates", []) or []:
                    fid = str(item.get("id"))
                    fc = item.get("forecast")
                    if fc and isinstance(fc, dict) and "w" in fc and "d" in fc and "l" in fc:
                        mapping[fid] = {"w": float(fc["w"]), "d": float(fc["d"]), "l": float(fc["l"]), "source": "understat"}
                _forecast_cache[key] = (now, mapping)
                return mapping

            # Build bounded candidate list (max 3 attempts).
            # Strategy: single inferred league/season where possible.
            # Use rosters team names only to keep primary league as EPL (most common);
            # try DEFAULT_SEASON then ±1 for primary league, then one fallback league.
            # This satisfies AT MOST 2 fetches for inference (base then base-1) plus 1 extra = 3 total.
            base = DEFAULT_SEASON
            candidates: list[tuple[str, int]] = []
            # primary league attempts: base, base-1, base+1 (truncate to leave room for other league)
            # we keep 2 for primary + 1 for next league to bound at 3
            candidates.append((LEAGUES[0], base))
            candidates.append((LEAGUES[0], base - 1))
            if len(candidates) < 3 and len(LEAGUES) > 1:
                candidates.append((LEAGUES[1], base))
            # dedupe and enforce max 3
            candidates = list(dict.fromkeys(candidates))[:3]

            for league, s in candidates:
                try:
                    mapping = await _get_forecast_map(league, s)
                    if target_id_str in mapping:
                        forecast = mapping[target_id_str]
                        break
                except Exception:
                    continue
        except Exception:
            forecast = None
        report["forecast"] = forecast
        return report

    async def discover_players(
        self,
        league_name: str = "EPL",
        season: int = DEFAULT_SEASON,
        position_group: str | None = None,
        minimum_minutes: float = 900,
        order_by: str = "npxG",
        limit: int = 20,
        start_date: str | None = None,
        end_date: str | None = None,
        seasons: list[int] | str | None = None,
        min_age: int | None = None,
        max_age: int | None = None,
        positions: list[str] | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        target_seasons = parse_seasons(seasons) or [season]

        import asyncio

        season_stats = await asyncio.gather(
            *(
                self.client.get_league_player_stats(
                    league_name, current_season, start_date=start_date, end_date=end_date
                )
                for current_season in target_seasons
            ),
            return_exceptions=True,
        )
        valid = [rows for rows in season_stats if isinstance(rows, list)]
        merged_by_id = _merge_league_players(valid)
        league_players = list(merged_by_id.values())

        filtered = [p for p in league_players if _minutes(p) >= minimum_minutes]
        from .analytics.percentiles import group_from_favorite, position_group as to_group

        favorites = await asyncio.gather(
            *(self._favorite_position(int(p.get("id", 0))) for p in filtered),
            return_exceptions=True,
        )
        player_groups = {}
        for p, favorite in zip(filtered, favorites):
            fav = favorite if isinstance(favorite, str) and favorite else None
            player_groups[int(p.get("id", 0))] = group_from_favorite(fav) or to_group(p.get("position"))
            p["_favorite_position"] = fav

        if position_group:
            filtered = [p for p in filtered if player_groups[int(p.get("id", 0))] == position_group.upper()]

        if positions:
            wanted = {pos.strip().upper() for pos in positions if pos and pos.strip()}
            if wanted:
                filtered = [
                    p for p in filtered
                    if (p.get("_favorite_position") or "").strip().upper() in wanted
                ]

        min_age = min_age if min_age is not None else None
        max_age = max_age if max_age is not None else None
        if min_age is not None or max_age is not None:
            names = [p.get("player_name") for p in filtered]
            birthdates = await self._birthdate_map(names, filtered)
            aged = []
            for p in filtered:
                age = _age(birthdates.get(p.get("player_name")))
                if age is None:
                    continue
                if min_age is not None and age < min_age:
                    continue
                if max_age is not None and age > max_age:
                    continue
                aged.append(p)
            filtered = aged

        if order_by in ("age_asc", "age_desc"):
            names = [p.get("player_name") for p in filtered]
            birthdates = await self._birthdate_map(names, filtered)
            keyed = {p.get("player_name"): _age(birthdates.get(p.get("player_name"))) for p in filtered}
            filtered.sort(key=lambda p: (keyed.get(p.get("player_name")) is None, keyed.get(p.get("player_name")) or 999))
            if order_by == "age_desc":
                filtered.reverse()
        else:
            filtered.sort(key=lambda p: _float(p, order_by), reverse=True)
        top = filtered[:limit]

        ppda_by_team = await self._team_press_map(league_name, target_seasons[-1], start_date, end_date)
        birthdates = await self._birthdate_map([p.get("player_name") for p in top], top)

        return {
            "league_name": league_name,
            "season": season,
            "seasons": target_seasons,
            "date_window": {"start_date": start_date, "end_date": end_date},
            "position_group": position_group,
            "minimum_minutes": minimum_minutes,
            "order_by": order_by,
            "limit": limit,
            "players": [
                {
                    "id": p.get("id"),
                    "name": p.get("player_name"),
                    "team": p.get("team_title"),
                    "position": p.get("position"),
                    "position_group": player_groups[int(p.get("id", 0))],
                    "favorite_position": p.get("_favorite_position"),
                    "age": _age(birthdates.get(p.get("player_name"))),
                    "date_of_birth": birthdates.get(p.get("player_name")),
                    "team_ppda": ppda_by_team.get(p.get("team_title")),
                    "team_oppda": ppda_by_team.get(f"{p.get('team_title')}::oppda"),
                    "minutes": int(_minutes(p)),
                    "npxG": _float(p, "npxG"),
                    "xA": _float(p, "xA"),
                    "xGChain": _float(p, "xGChain"),
                    "xGBuildup": _float(p, "xGBuildup"),
                    "goals": _float(p, "goals"),
                    "assists": _float(p, "assists"),
                    "yellow_cards": _float(p, "yellow_cards"),
                    "red_cards": _float(p, "red_cards"),
                    "npg": _float(p, "npg"),
                    "npxG_per90": _per90_value(p, "npxG"),
                    "xA_per90": _per90_value(p, "xA"),
                    "goal_involvement_per90": round(_per90_value(p, "npxG") + _per90_value(p, "xA"), 3),
                    "xG_per_shot": _ratio_value(p, "xG", "shots"),
                    "conversion": _ratio_value(p, "goals", "shots"),
                    "g_minus_xg": round(_float(p, "goals") - _float(p, "xG"), 2),
                }
                for p in top
            ],
            "limitations": [
                "Age comes from Wikidata (CC0); a few players may be missing or mismatched on name — shown as '—' rather than guessed.",
                "Per-player pressing counts do not exist in Understat; the team PPDA column is the honest pressing context.",
                "Team PPDA is the full-season team value (not date-windowed per player).",
                "Multi-season discovery merges counting stats and keeps the latest team; team PPDA is from the latest season only.",
            ],
        }

    async def player_shot_map(
        self,
        player_id: int | None = None,
        player_name: str | None = None,
        league_name: str = "EPL",
        season: int = DEFAULT_SEASON,
        start_date: str | None = None,
        end_date: str | None = None,
        seasons: list[int] | str | None = None,
    ) -> dict:
        if player_id is None and player_name is None:
            raise ValueError("Either player_id or player_name is required.")

        start_date, end_date = _valid_date_range(start_date, end_date)
        target_seasons = parse_seasons(seasons) or [season]

        if player_id is None:
            matches = await self.client.search_players(player_name)
            if not matches:
                raise ValueError(f"Player '{player_name}' was not found via Understat search.")
            player_id = int(matches[0]["id"])
            player_name = matches[0].get("player") or matches[0].get("player_name") or player_name

        raw_shots = await self.client.get_player_shots(player_id)
        shots = _filter_shots_to_seasons(raw_shots, target_seasons, start_date, end_date)

        shot_points = []
        for s in shots:
            shot_points.append(
                {
                    "minute": s.get("minute"),
                    "xG": round(float(s.get("xG") or 0), 4),
                    "result": s.get("result"),
                    "situation": s.get("situation"),
                    "shotType": s.get("shotType"),
                    "lastAction": s.get("lastAction"),
                    "player": s.get("player") or player_name,
                    "X": float(s.get("X") or 0),
                    "Y": float(s.get("Y") or 0),
                    "date": (s.get("date") or "")[:10],
                    "h_a": s.get("h_a"),
                    "h_team": s.get("h_team"),
                    "a_team": s.get("a_team"),
                    "season": s.get("season"),
                }
            )

        goals = sum(1 for s in shot_points if s["result"] == "Goal")
        total_xg = sum(s["xG"] for s in shot_points)

        return {
            "player_id": player_id,
            "player_name": player_name,
            "seasons": target_seasons,
            "total_shots": len(shot_points),
            "goals": goals,
            "total_xG": round(total_xg, 2),
            "shots": shot_points,
            "date_window": {"start_date": start_date, "end_date": end_date},
        }

    async def team_shot_map(
        self,
        team_name: str,
        league_name: str = "EPL",
        season: int = DEFAULT_SEASON,
        start_date: str | None = None,
        end_date: str | None = None,
        seasons: list[int] | str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        target_seasons = parse_seasons(seasons) or [season]

        import asyncio

        all_results = []
        for s in target_seasons:
            try:
                results = await self.client.get_team_results(team_name, s)
                all_results.extend(as_list_matches(results))
            except Exception:
                pass

        if start_date or end_date:
            all_results = _filter_rows_by_date(all_results, start_date, end_date)

        match_ids = [int(m["id"]) for m in all_results if m.get("id")]
        target_match_ids = match_ids[:76]

        all_match_shots = await asyncio.gather(
            *(self.client.get_match_shots(mid) for mid in target_match_ids),
            return_exceptions=True,
        )

        for_shots = []
        against_shots = []

        for match_info, batch in zip(all_results[:len(target_match_ids)], all_match_shots):
            if isinstance(batch, BaseException) or not isinstance(batch, dict):
                continue
            h_team = (match_info.get("h") or {}).get("title") or match_info.get("side")
            is_home = (h_team == team_name) if h_team else (match_info.get("h_a") == "h")

            for_side = "h" if is_home else "a"
            against_side = "a" if is_home else "h"

            for s in batch.get(for_side, []):
                for_shots.append(
                    {
                        "minute": s.get("minute"),
                        "xG": round(float(s.get("xG") or 0), 4),
                        "result": s.get("result"),
                        "situation": s.get("situation"),
                        "shotType": s.get("shotType"),
                        "lastAction": s.get("lastAction"),
                        "player": s.get("player"),
                        "X": float(s.get("X") or 0),
                        "Y": float(s.get("Y") or 0),
                        "date": (s.get("date") or "")[:10],
                        "season": s.get("season"),
                    }
                )

            for s in batch.get(against_side, []):
                against_shots.append(
                    {
                        "minute": s.get("minute"),
                        "xG": round(float(s.get("xG") or 0), 4),
                        "result": s.get("result"),
                        "situation": s.get("situation"),
                        "shotType": s.get("shotType"),
                        "lastAction": s.get("lastAction"),
                        "player": s.get("player"),
                        "X": float(s.get("X") or 0),
                        "Y": float(s.get("Y") or 0),
                        "date": (s.get("date") or "")[:10],
                        "season": s.get("season"),
                    }
                )

        return {
            "team_name": team_name,
            "league_name": league_name,
            "seasons": target_seasons,
            "matches_analyzed": len(target_match_ids),
            "for_shots": for_shots,
            "against_shots": against_shots,
            "for_xG": round(sum(s["xG"] for s in for_shots), 2),
            "against_xG": round(sum(s["xG"] for s in against_shots), 2),
            "for_goals": sum(1 for s in for_shots if s["result"] == "Goal"),
            "against_goals": sum(1 for s in against_shots if s["result"] == "Goal"),
            "date_window": {"start_date": start_date, "end_date": end_date},
        }

    _favorite_cache: dict[int, str] = {}

    async def _favorite_position(self, player_id: int) -> str | None:
        if player_id in self._favorite_cache:
            return self._favorite_cache[player_id]
        try:
            data = await self.client.get_player_data(player_id)
            favorite = (data.get("player") or {}).get("favorite_position")
        except Exception:
            favorite = None
        self._favorite_cache[player_id] = favorite
        return favorite

    async def _team_press_map(self, league_name, season, start_date, end_date):
        try:
            table = await self.client.get_league_table(
                league_name, season, start_date=start_date, end_date=end_date
            )
        except Exception:
            return {}
        mapping = {}
        rows = table[1:] if table and table[0] and str(table[0][0]).strip().lower() == "team" else (table or [])
        for row in rows:
            if not row or not row[0]:
                continue
            if len(row) > 13:
                mapping[str(row[0])] = _to_float(row[13])
            if len(row) > 14:
                mapping[f"{str(row[0])}::oppda"] = _to_float(row[14])
        return mapping

    async def _birthdate_map(self, names: list[str], players: list[dict]) -> dict:
        from .stat_data.wikidata import fetch_birthdates
        hints = {p.get("player_name"): p.get("team_title") for p in players if p.get("team_title")}
        try:
            return await fetch_birthdates([n for n in names if n], hints)
        except Exception:
            return {}


def _find_team_row(table, team_name: str):
    rows = table[1:] if table and table[0] and str(table[0][0]).strip().lower() == "team" else (table or [])
    return next((r for r in rows if str(r[0]).lower() == team_name.lower()), None)


def _filter_history(history, start_date: str | None, end_date: str | None):
    rows = as_list_matches(history)
    if not start_date and not end_date:
        return rows
    filtered = []
    for row in rows:
        current = (row.get("date") or "")[:10]
        if not current:
            filtered.append(row)
            continue
        if start_date and current < start_date:
            continue
        if end_date and current > end_date:
            continue
        filtered.append(row)
    return filtered


def _merge_league_players(season_rows_list: list[list[dict]]) -> dict[int, dict]:
    """Merge per-season league player rows into one row per player id.

    Counting stats sum across seasons (time, goals, xG, ...); team and position
    come from the most recent season in which the player appears.
    """
    SUM_KEYS = (
        "games", "time", "goals", "xG", "npxG", "npg", "assists", "xA", "shots",
        "key_passes", "xGChain", "xGBuildup", "yellow_cards", "red_cards",
    )
    merged: dict[int, dict] = {}
    for season_index, rows in enumerate(season_rows_list):
        for row in rows:
            player_id = int(row.get("id", 0))
            if not player_id:
                continue
            if player_id not in merged:
                merged[player_id] = dict(row)
            else:
                for key in SUM_KEYS:
                    merged[player_id][key] = str(_to_float(merged[player_id].get(key)) + _to_float(row.get(key)))
                # keep the latest season's identity fields
                merged[player_id]["team_title"] = row.get("team_title", merged[player_id].get("team_title"))
                merged[player_id]["position"] = row.get("position", merged[player_id].get("position"))
    return merged


def _filter_shots_to_seasons(raw_shots, seasons: list[int], start_date=None, end_date=None) -> list[dict]:
    rows = list(raw_shots.values()) if isinstance(raw_shots, dict) else list(raw_shots or [])
    allowed = {str(season) for season in seasons}
    filtered = [row for row in rows if str(row.get("season")) in allowed]
    if start_date or end_date:
        filtered = _filter_rows_by_date(filtered, start_date, end_date)
    return filtered


def _filter_rows_by_date(rows, start_date=None, end_date=None):
    if not start_date and not end_date:
        return rows
    out = []
    for row in rows:
        current = (row.get("date") or "")[:10]
        if not current:
            out.append(row)
            continue
        if start_date and current < start_date:
            continue
        if end_date and current > end_date:
            continue
        out.append(row)
    return out


def _merge_table_rows(team_rows: list[list]) -> list:
    """Merge per-season league-table rows for the same team into one row.

    Column layout: [Team, M, W, D, L, G, GA, PTS, xG, NPxG, xGA, NPxGA, NPxGD,
    PPDA, OPPDA, DC, ODC, xPTS]. Counting columns sum; ratio columns (PPDA,
    OPPDA) take the minutes-weighted... simplest honest rule: sums for counts,
    and for PPDA/OPPDA use the most recent season's value (they are per-season
    rate metrics, not additive).
    """
    if len(team_rows) == 1:
        return team_rows[0]
    merged = [team_rows[-1][0]]
    for col in range(1, len(team_rows[0])):
        if col in (13, 14):  # PPDA / OPPDA: keep the latest season's rate
            merged.append(team_rows[-1][col])
        else:
            merged.append(sum(_to_float(row[col]) if col != 1 else _to_int(row[col]) for row in team_rows if len(row) > col))
    return merged


def _find_team_row(table, team_name: str):
    rows = table[1:] if table and table[0] and str(table[0][0]).strip().lower() == "team" else (table or [])
    return next((r for r in rows if str(r[0]).lower() == team_name.lower()), None)


def _window_label(start_date, end_date):
    if start_date and end_date:
        return f" between {start_date} and {end_date}"
    if start_date:
        return f" from {start_date}"
    if end_date:
        return f" until {end_date}"
    return ""


def _float(row: dict, key: str) -> float:
    try:
        return round(float(row.get(key, 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def _per90_value(row: dict, key: str) -> float:
    minutes = _minutes(row)
    if minutes <= 0:
        return 0.0
    return round(_float(row, key) * 90.0 / minutes, 3)


def _ratio_value(row: dict, numerator_key: str, denominator_key: str) -> float:
    denominator = _float(row, denominator_key)
    if denominator <= 0:
        return 0.0
    return round(_float(row, numerator_key) / denominator, 3)


def _age(date_of_birth: str | None) -> int | None:
    if not date_of_birth:
        return None
    try:
        from datetime import date, datetime
        born = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except (ValueError, TypeError):
        return None


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _minutes(row: dict) -> float:
    try:
        return float(row.get("time", 0))
    except (TypeError, ValueError):
        return 0.0
